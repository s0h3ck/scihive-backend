import logging
from datetime import datetime

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import (Api, Resource, abort, fields, inputs, marshal_with,
                           reqparse)
from typing import List
from src.new_backend.models import Collection, Paper, db, user_collection_table, User

from .user_utils import get_user_by_email

app = Blueprint('groups', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


class Count(fields.Raw):
    def format(self, value):
        return len(value)


group_fields = {
    'id': fields.String,
    'name': fields.String,
    'created_at': fields.DateTime(dt_format='rfc822', attribute='creation_date'),
    'color': fields.String,
}


def get_user_groups(user: User) -> List[Collection]:
    return Collection.query.filter(Collection.users.any(email=user.email)).all()


def get_user_groups_by_email(email: str) -> List[Collection]:
    return Collection.query.filter(Collection.users.any(email=email)).order_by(Collection.name).all()


class Groups(Resource):
    method_decorators = [jwt_required]

    @marshal_with(group_fields)
    def get(self):
        email = get_jwt_identity()
        return get_user_groups_by_email(email)

    @marshal_with(group_fields)
    def post(self):
        # Join to group in addition to getting the list
        user = get_user_by_email()
        parser = reqparse.RequestParser()
        parser.add_argument('id', help='This field cannot be blank', required=True)
        data = parser.parse_args()
        group = Collection.query.get_or_404(data.get('id'))
        group.users.append(user)
        db.session.commit()
        return get_user_groups(user)


class NewGroup(Resource):
    method_decorators = [jwt_required]

    @marshal_with({'groups': fields.List(fields.Nested(group_fields)), 'new_id': fields.String})
    def post(self):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('name', help='This field cannot be blank', required=True)
        parser.add_argument('color', required=False, type=str)
        data = parser.parse_args()
        user = get_user_by_email(current_user)
        collection = Collection(creation_date=datetime.utcnow(), name=data.get('name'),
                                color=data.get('color'), created_by_id=user.id)
        collection.users.append(user)
        db.session.add(collection)
        db.session.commit()
        all_collections = get_user_groups(user)
        response = {'groups': all_collections, 'new_id': collection.id}
        return response


extended_group_fields = dict(group_fields)
extended_group_fields['num_papers'] = fields.Integer


class Group(Resource):
    @marshal_with(extended_group_fields)
    def get(self, group_id: str):
        group = Collection.query.get_or_404(group_id)
        group_dict = group.__dict__
        group_dict['num_papers'] = len(group.papers)
        return group_dict

    @jwt_required
    @marshal_with(group_fields)
    def delete(self, group_id: str):
        group = Collection.query.get_or_404(group_id)
        user = get_user_by_email()
        try:
            group.users.remove(user)
            db.session.commit()
        except ValueError:
            pass
        return get_user_groups(user)

    @jwt_required
    @marshal_with(group_fields)
    def patch(self, group_id: str):
        user = get_user_by_email()
        group = Collection.query.get_or_404(group_id)
        if group.created_by != user:
            abort(403, message="Only group owner can edit group")
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=False, type=str)
        parser.add_argument('color', required=False, type=str)
        data = parser.parse_args()
        for key in data:
            setattr(group, key, data[key])
        db.session.commit()
        return get_user_groups(user)

    @jwt_required
    @marshal_with(group_fields)
    def post(self, group_id):
        parser = reqparse.RequestParser()
        parser.add_argument('paper_id', required=True, help="paper_id is missing")
        parser.add_argument('add', required=True,
                            help="should specify if add (add=1) or remove (add=0)", type=inputs.boolean)
        data = parser.parse_args()
        user = get_user_by_email()
        paper = Paper.query.get_or_404(data.get('paper_id'))
        group = Collection.query.get_or_404(group_id)
        if (data.get('add')):
            group.papers.append(paper)
        else:
            try:
                group.papers.remove(paper)
            except ValueError:
                pass

        # TODO: optimize this:
        paper.num_stars = len(paper.collections)
        db.session.commit()
        return {'message': 'success'}


api.add_resource(Groups, '/all')
api.add_resource(NewGroup, '/new')
api.add_resource(Group, '/group/<group_id>')
