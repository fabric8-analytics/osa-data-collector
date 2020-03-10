import itertools
import logging
import os
import warnings
from typing import List, Dict

import arrow
import daiquiri
import pandas as pd

import src.utils.cloud_constants as cc
from src.utils import bq_client_helper

warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=Warning)

daiquiri.setup(level=logging.INFO)
_logger = daiquiri.getLogger(__name__)


class BigQueryDataCollector:
    def __init__(self, repos: List[str], bq_credentials_path: str = '', days: int = 3):
        self._bq_client = BigQueryDataCollector._get_bq_client(bq_credentials_path)
        self._golang_repo = bq_client_helper.get_gokube_trackable_repos(repo_dir=cc.GOKUBE_REPO_LIST)
        self._knative_repo = bq_client_helper.get_gokube_trackable_repos(repo_dir=cc.KNATIVE_REPO_LIST)
        self._kubevirt_repo = bq_client_helper.get_gokube_trackable_repos(repo_dir=cc.KUBEVIRT_REPO_LIST)
        self._init_query_param(repos, days)

    def _get_repo_by_eco_system(self, eco_system: str) -> List[str]:
        if eco_system == 'openshift':
            return self._golang_repo
        elif eco_system == 'knative':
            return self._knative_repo
        elif eco_system == 'kubevirt':
            return self._kubevirt_repo

    def _get_repo_list(self, eco_systems: List[str]) -> List[str]:
        repo_names = list()
        for eco_system in eco_systems:
            print(eco_system)
            repo_names.append(self._get_repo_by_eco_system(eco_system))
        return list(itertools.chain(*repo_names))

    @staticmethod
    def _get_repo_url(eco_system: str) -> str:
        repo_list_url = None
        _logger.info("Eco-System to Track {eco}".format(eco=eco_system))
        if eco_system == 'openshift':
            repo_list_url = cc.GOKUBE_REPO_LIST
        elif eco_system == 'knative':
            repo_list_url = cc.KNATIVE_REPO_LIST
        elif eco_system == 'kubevirt':
            repo_list_url = cc.KUBEVIRT_REPO_LIST
        return repo_list_url

    @classmethod
    def _get_bq_client(cls, bq_credentials_path):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS',
                                                                      bq_credentials_path or '')
        return bq_client_helper.create_github_bq_client()

    @staticmethod
    def _get_query_date_range(no_of_days):
        # Don't change this
        present_time = arrow.now()

        # CHANGE NEEDED
        # to get data for N days back starting from YESTERDAY
        # e.g if today is 20190528 and DURATION DAYS = 2 -> BQ will get data for 20190527, 20190526
        # We don't get data for PRESENT DAY since github data will be incomplete on the same day
        # But you can get it if you want but better not to for completeness :)

        # You can set this directly from command line using the -d or --days-since-yday argument
        duration_days = no_of_days or 3  # Gets 3 days of previous data including YESTERDAY

        # Don't change this
        # Start time for getting data
        start_time = present_time.shift(days=-duration_days)

        # Don't change this
        # End time for getting data (present_time - 1) i.e yesterday
        # you can remove -1 to get present day data
        # but it is not advised as data will be incomplete
        end_time = present_time.shift(days=-1)

        last_n_days = [dt.format('YYYYMMDD') for dt in arrow.Arrow.range('day', start_time, end_time)]
        return last_n_days, start_time, end_time

    # TODO - We are hardcoding 'golang' as ecosystem, need to figure out how we can set differnt eco systems
    def _get_gh_event_as_data_frame(self, query_param: Dict) -> pd.DataFrame:
        event_query = r"""
        SELECT
            repo.name as repo_name,
            type as event_type,
            JSON_EXTRACT_SCALAR(payload, '$.action') as status,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.id') as id,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.number') as number,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.url') as api_url,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.html_url') as url,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.user.login') as creator_name,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.user.html_url') as creator_url,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.created_at') as created_at,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.updated_at') as updated_at,
            JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.closed_at') as closed_at,
            TRIM(REGEXP_REPLACE(
                     REGEXP_REPLACE(
                         JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.title'),
                         r'\r\n|\r|\n',
                         ' '),
                     r'\s{2,}',
                     ' ')) as title,
            TRIM(REGEXP_REPLACE(
                     REGEXP_REPLACE(
                         JSON_EXTRACT_SCALAR(payload, '$.{payload_field_name}.body'),
                         r'\r\n|\r|\n',
                         ' '),
                     r'\s{2,}',
                     ' ')) as body

        FROM `githubarchive.day.{year_prefix_wildcard}`
            WHERE _TABLE_SUFFIX IN {year_suffix_month_day}
            AND repo.name in {repo_names}
            AND type = '{event_type}'
            """

        _logger.debug("Query: {qry}".format(qry=event_query))
        _logger.info('Event type: {event_type}'.format(event_type=query_param['{event_type}']))

        event_query = bq_client_helper.bq_add_query_params(event_query, query_param)
        qsize = self._bq_client.estimate_query_size(event_query)
        _logger.info('Retrieving GH Events. Query cost in GB={qc}'.format(qc=qsize))

        df = self._bq_client.query_to_pandas(event_query)
        if df.empty:
            _logger.warn('No Events present for given time duration.')
        else:
            _logger.info('Total Events retrieved: {n}'.format(n=len(df)))

            df.created_at = pd.to_datetime(df.created_at)
            df.updated_at = pd.to_datetime(df.updated_at)
            df.closed_at = pd.to_datetime(df.closed_at)
            # From the duplicate records based on url take the last updated record.
            df = df.loc[df.groupby('url').updated_at.idxmax(skipna=False)].reset_index(drop=True)
            _logger.info('Total Events after deduplication: {n}'.format(n=len(df)))

        return df

    def _init_query_param(self, eco_systems: List[str], days: int) -> None:
        last_n_days = self._get_query_date_range(days)[0]
        repo_names = self._get_repo_list(eco_systems)

        # Don't change this
        year_prefix = '20*'
        day_list = [item[2:] for item in last_n_days]
        import pprint
        pprint.pprint(day_list)
        pprint.pprint(year_prefix)
        query_params = {'{year_prefix_wildcard}': year_prefix,
                        '{year_suffix_month_day}': '(' + ', '.join(["'" + d + "'" for d in day_list]) + ')',
                        '{repo_names}': '(' + ', '.join(["'" + r + "'" for r in repo_names]) + ')', }
        self._query_params, self._last_n_days = query_params, last_n_days

    def get_gh_event_estimate(self):
        query = """
        SELECT  type as EventType, count(*) as Freq
                FROM `githubarchive.day.{year_prefix_wildcard}`
                WHERE _TABLE_SUFFIX IN {year_suffix_month_day}
                AND repo.name in {repo_names}
                AND type in ('PullRequestEvent', 'IssuesEvent')
                GROUP BY type
        """
        query = bq_client_helper.bq_add_query_params(query, self._query_params)
        return self._bq_client.query_to_pandas(query)

    def get_issues_as_data_frame(self) -> pd.DataFrame:
        """
        Retrieves GH Issues as pandas data frame
        """
        return self._get_gh_event_as_data_frame(
            {**self._query_params, **{'{payload_field_name}': 'issue', '{event_type}': 'IssuesEvent'}})

    def get_prs_as_data_frame(self) -> pd.DataFrame:
        """
        Retrieves GH PRs as pandas data frame
        """
        return self._get_gh_event_as_data_frame(
            {**self._query_params, **{'{payload_field_name}': 'pull_request', '{event_type}': 'PullRequestEvent'}})

    def get_github_data(self) -> pd.DataFrame:
        """
        Retrives GH Issues and PRs and merge it into single dataframe
        """
        issues_df = self.get_issues_as_data_frame()
        prs_df = self.get_prs_as_data_frame()

        _logger.info('Merging issues and pull requests datasets')
        cols = issues_df.columns
        data_frame = pd.concat([issues_df, prs_df], axis=0, sort=False, ignore_index=True).reset_index(drop=True)
        data_frame = data_frame[cols]

        # update eco-system
        if not data_frame.empty:
            _logger.info('Updating eco-system')
            data_frame['ecosystem'] = data_frame.apply(lambda x: self._update_eco_system(x['repo_name']),
                                                       axis=1)

        return data_frame

    def _update_eco_system(self, repo_name):
        """
        Update ecosystem based on repo_name
        """
        if repo_name in self._golang_repo:
            return 'golang'
        elif repo_name in self._knative_repo:
            return 'knative'
        elif repo_name in self._kubevirt_repo:
            return 'kubevirt'
        else:
            return None

    def save_data_to_object_store(self, data_frame, days_since_yday):
        """
        Save the github data to object s3 store
        """
        if data_frame.empty:
            _logger.warn('Nothing to save')
        else:

            last_n_days, start_time, end_time = self._get_query_date_range(days_since_yday)
            file_name = "gh_data_{days}.csv".format(
                days='-'.join([start_time.format('YYYYMMDD'), end_time.format('YYYYMMDD')]))
            _logger.info('Uploading Github data to S3 Bucket')
            try:
                data_frame.to_csv(
                    's3://{bucket}/gh_data/{filename}'.format(bucket=cc.AWS_S3_BUCKET_NAME, filename=file_name),
                    index=False)
            except Exception as ex:
                _logger.error("Exception occurred while saving data to object store. Msg: {msg}".format(msg=ex))
            _logger.info('Upload completed')

    @property
    def last_n_days(self):
        return self._last_n_days
