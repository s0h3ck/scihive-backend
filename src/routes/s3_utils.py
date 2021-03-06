import hashlib
import os
import urllib
import boto3
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('S3_KEY'),
    aws_secret_access_key=os.environ.get('S3_SECRET'),
)

BUCKET = os.environ.get('S3_BUCKET_NAME')
PREFIX = 'papers'


def exists(key):
    """return the key's size if it exist, else None"""
    response = s3.list_objects_v2(
        Bucket=BUCKET,
        Prefix=key,
    )
    for obj in response.get('Contents', []):
        if obj['Key'] == key:
            return True
    return False


def key_to_url(key, with_prefix=False):
    url = f'https://{BUCKET}'
    if with_prefix:
        url += f'/{PREFIX}'
    url += f'/{key}'
    return url


def arxiv_to_s3(url):
    id_with_ver = url.split('/')[-1]
    key = f'{PREFIX}/{id_with_ver}'
    if exists(key):
        return key_to_url(key)

    pdf = urllib.request.urlopen(url)
    s3.upload_fileobj(pdf, BUCKET, key)
    return key_to_url(key)


def upload_to_s3(md5: str, file_stream):
    key = f'{PREFIX}/{md5}.pdf'
    if exists(key):
        return True
    file_stream.seek(0)
    s3.upload_fileobj(file_stream, BUCKET, key)
    return False


def calc_md5(content):
    return hashlib.md5(content).hexdigest()
