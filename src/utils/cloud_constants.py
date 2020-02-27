"""
This file contains the constants for interaction with AWS/Github Repo.
Note: Please don't add keys directly here, refer to environment variables
"""
import os

# Please make sure you have your AWS envt variables setup
AWS_S3_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_S3_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
S3_BUCKET_NAME = os.environ.get('AWS_S3_BUCKET_NAME', '')

# Please set the following to point to your BQ auth credentials JSON
BIGQUERY_CREDENTIALS_FILEPATH = os.environ.get('BIGQUERY_CREDENTIALS_FILEPATH', '../../auth/bq_key.json')

GOKUBE_REPO_LIST = os.environ.get('GOKUBE_REPO_LIST', 'src/utils/data_assets/golang-repo-list.txt')
KNATIVE_REPO_LIST = os.environ.get('KNATIVE_REPO_LIST', 'src/utils/data_assets/knative-repo-list.txt')
KUBEVIRT_REPO_LIST = os.environ.get('KUBEVIRT_REPO_LIST', 'src/utils/data_assets/kubevirt-repo-list.txt')