from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import call, patch, Mock

from dateutil.parser import isoparse
from django.conf import settings
from django.http import HttpRequest
from asgiref.sync import async_to_sync

import mwclient
import mwclient.util
import mwclient.errors

from wiki_interface.data import WikiContrib, LogEvent
from wiki_interface.wiki import Wiki, Page
from wiki_interface.block_utils import BlockEvent, UnblockEvent


class ConstructorTest(TestCase):
    # pylint: disable=invalid-name

    @patch('wiki_interface.wiki.Site')
    def test_default(self, mock_Site):
        Wiki()

        mock_Site.assert_called_once()
        args, kwargs = mock_Site.call_args
        self.assertEqual(args, (settings.MEDIAWIKI_SITE_NAME,))
        self.assertEqual(kwargs, {'clients_useragent': settings.MEDIAWIKI_USER_AGENT})


    @patch('wiki_interface.wiki.Site')
    @patch('django.contrib.auth.get_user')
    def test_anonymous(self, mock_get_user, mock_Site):
        mock_get_user().is_anonymous = True

        Wiki(HttpRequest())

        mock_Site.assert_called_once()
        args, kwargs = mock_Site.call_args
        self.assertEqual(args, (settings.MEDIAWIKI_SITE_NAME,))
        self.assertEqual(kwargs, {'clients_useragent': settings.MEDIAWIKI_USER_AGENT})


    @patch('wiki_interface.wiki.Site')
    @patch('django.contrib.auth.get_user')
    def test_authenticated(self, mock_get_user, mock_Site):
        mock_get_user().is_anonymous = False

        Wiki(HttpRequest())

        mock_Site.assert_called_once()
        args, kwargs = mock_Site.call_args
        self.assertEqual(args, (settings.MEDIAWIKI_SITE_NAME,))
        self.assertEqual(set(kwargs.keys()), {'clients_useragent',
                                              'consumer_token',
                                              'consumer_secret',
                                              'access_token',
                                              'access_secret'})
        self.assertEqual(kwargs['clients_useragent'], settings.MEDIAWIKI_USER_AGENT)


class NamespaceTest(TestCase):
    # pylint: disable=invalid-name

    @patch('wiki_interface.wiki.Site')
    def test_namespaces(self, mock_Site):
        mock_Site().namespaces = {0: '',
                                  1: 'Whatever'}
        wiki = Wiki()

        self.assertEqual(wiki.namespaces[0], '')
        self.assertEqual(wiki.namespaces[1], 'Whatever')
        self.assertEqual(wiki.namespace_values[''], 0)
        self.assertEqual(wiki.namespace_values['Whatever'], 1)


class WikiContribTest(TestCase):
    def test_construct_default(self):
        contrib = WikiContrib(999, datetime(2020, 7, 30), 'user', 0, 'title', 'comment')
        self.assertEqual(contrib.timestamp, datetime(2020, 7, 30))
        self.assertEqual(contrib.user_name, 'user')
        self.assertEqual(contrib.title, 'title')
        self.assertEqual(contrib.comment, 'comment')
        self.assertTrue(contrib.is_live)


    def test_construct_live_true(self):
        contrib = WikiContrib(999, datetime(2020, 7, 30), 'user', 0, 'title', 'comment', is_live=True)
        self.assertEqual(contrib.timestamp, datetime(2020, 7, 30))
        self.assertEqual(contrib.user_name, 'user')
        self.assertEqual(contrib.title, 'title')
        self.assertEqual(contrib.comment, 'comment')
        self.assertTrue(contrib.is_live)


    def test_construct_live_false(self):
        contrib = WikiContrib(999, datetime(2020, 7, 30), 'user', 0, 'title', 'comment', is_live=False)
        self.assertEqual(contrib.timestamp, datetime(2020, 7, 30))
        self.assertEqual(contrib.user_name, 'user')
        self.assertEqual(contrib.title, 'title')
        self.assertEqual(contrib.comment, 'comment')
        self.assertFalse(contrib.is_live)


class UserContributionsTest(TestCase):
    # pylint: disable=invalid-name

    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_with_string(self, mock_Site):
        mock_Site().usercontributions.return_value = [
            {'revid': 20200730, 'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0),
             'ns': 0, 'user': 'fred', 'title': 'p1', 'comment': 'c1', 'tags': []},
            {'revid': 20200729, 'timestamp': (2020, 7, 29, 0, 0, 0, 0, 0, 0),
             'ns': 0, 'user': 'fred', 'title': 'p2', 'comment': 'c2', 'tags': []}]
        wiki = Wiki()

        contributions = list(wiki.user_contributions('fred'))

        mock_Site().usercontributions.assert_called_once_with(
            'fred',
            prop='ids|title|timestamp|comment|flags|tags',
            show='',
            end=None)
        self.assertIsInstance(contributions[0], WikiContrib)
        self.assertEqual(contributions, [
            WikiContrib(20200730, datetime(2020, 7, 30, tzinfo=timezone.utc), 'fred', 0, 'p1', 'c1'),
            WikiContrib(20200729, datetime(2020, 7, 29, tzinfo=timezone.utc), 'fred', 0, 'p2', 'c2')])


    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_with_list_of_strings(self, mock_Site):
        mock_Site().usercontributions.return_value = [
            {'revid': 20200730, 'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0),
             'user': 'bob', 'ns': 0, 'title': 'p1', 'comment': 'c1', 'tags': []},
            {'revid': 20200729, 'timestamp': (2020, 7, 29, 0, 0, 0, 0, 0, 0),
             'user': 'bob', 'ns': 0, 'title': 'p2', 'comment': 'c2', 'tags': []},
            {'revid': 20200728, 'timestamp': (2020, 7, 28, 0, 0, 0, 0, 0, 0),
             'user': 'alice', 'ns': 0, 'title': 'p3', 'comment': 'c3', 'tags': []}]
        wiki = Wiki()

        contributions = list(wiki.user_contributions(['bob', 'alice']))

        mock_Site().usercontributions.assert_called_once_with(
            'bob|alice',
            prop='ids|title|timestamp|comment|flags|tags',
            show='',
            end=None)
        self.assertIsInstance(contributions[0], WikiContrib)
        self.assertEqual(contributions, [
            WikiContrib(20200730, datetime(2020, 7, 30, tzinfo=timezone.utc), 'bob', 0, 'p1', 'c1'),
            WikiContrib(20200729, datetime(2020, 7, 29, tzinfo=timezone.utc), 'bob', 0, 'p2', 'c2'),
            WikiContrib(20200728, datetime(2020, 7, 28, tzinfo=timezone.utc), 'alice', 0, 'p3', 'c3')])


    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_raises_value_error_with_pipe_in_name(self, mock_Site):
        mock_Site().usercontributions.return_value = iter([])
        wiki = Wiki()

        with self.assertRaises(ValueError):
            list(wiki.user_contributions('foo|bar'))


    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_with_too_many_names(self, mock_Site):
        mock_Site().usercontributions.side_effect = [
            [{'revid': 20200729,
              'timestamp': (2020, 7, 29, 0, 0, 0, 0, 0, 0),
              'user': '0',
              'ns': 0,
              'title': 'p1',
              'comment': 'c1',
              'tags': []}],
            [{'revid': 20200730,
              'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0),
              'user': '1',
              'ns': 0,
              'title': 'p2',
              'comment': 'c2',
              'tags': []}],
        ]
        wiki = Wiki()

        # This is a hack.  In theory, we should paramaterize the test
        # to work with any value of MAX_UCUSER.  In practice, doing so
        # is just more effort (and complicated test code) than is
        # worth it.  At least this future-proofs us a bit.
        self.assertEqual(wiki.MAX_UCUSER, 50)

        user_names = [str(i) for i in range(55)]
        contributions = list(wiki.user_contributions(user_names))

        self.assertEqual(mock_Site().usercontributions.call_args_list,
                         [call('0|1|2|3|4|5|6|7|8|9'
                               '|10|11|12|13|14|15|16|17|18|19'
                               '|20|21|22|23|24|25|26|27|28|29'
                               '|30|31|32|33|34|35|36|37|38|39'
                               '|40|41|42|43|44|45|46|47|48|49',
                               prop='ids|title|timestamp|comment|flags|tags',
                               show='',
                               end=None),
                          call('50|51|52|53|54',
                               prop='ids|title|timestamp|comment|flags|tags',
                               show='',
                               end=None),
                         ])
        self.assertEqual(contributions, [
            WikiContrib(20200729, datetime(2020, 7, 29, tzinfo=timezone.utc), '0', 0, 'p1', 'c1'),
            WikiContrib(20200730, datetime(2020, 7, 30, tzinfo=timezone.utc), '1', 0, 'p2', 'c2')])


    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_returns_tags(self, mock_Site):
        mock_Site().usercontributions.return_value = [
            {'revid': 999,
             'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0),
             'ns': 0,
             'user': 'fred',
             'title': 'p1',
             'comment': 'c1',
             'tags': ['t1', 't2'],
            }]
        wiki = Wiki()

        contributions = list(wiki.user_contributions('fred'))

        self.assertEqual(contributions, [WikiContrib(999,
                                                     datetime(2020, 7, 30, tzinfo=timezone.utc),
                                                     'fred',
                                                     0,
                                                     'p1',
                                                     'c1',
                                                     tags=['t1', 't2'])])


    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_handles_supressed_comment(self, mock_Site):
        mock_Site().usercontributions.return_value = [
            {'revid': 999,
             'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0),
             'ns': 0,
             'user': 'fred',
             'title': 'p1',
             'commenthidden': '',
             'tags': ['t1', 't2'],
            }]
        wiki = Wiki()

        contributions = list(wiki.user_contributions('fred'))

        self.assertEqual(contributions, [WikiContrib(999,
                                                     datetime(2020, 7, 30, tzinfo=timezone.utc),
                                                     'fred',
                                                     0,
                                                     'p1',
                                                     None,
                                                     tags=['t1', 't2'])])


    @patch('wiki_interface.wiki.Site')
    def test_user_contributions_accepts_end_parameter(self, mock_Site):
        mock_Site().usercontributions.return_value = []
        wiki = Wiki()

        contributions = list(wiki.user_contributions('fred', end='2020-01-01T00:00:00'))

        mock_Site().usercontributions.assert_called_once_with(
            'fred',
            prop='ids|title|timestamp|comment|flags|tags',
            show='',
            end='2020-01-01T00:00:00')
        self.assertEqual(contributions, [])


class DeletedUserContributionsTest(TestCase):
    # pylint: disable=invalid-name

    @patch('wiki_interface.wiki.List')
    def test_deleted_user_contributions_with_single_page(self, mock_List):
        # See https://www.mediawiki.org/wiki/API:Alldeletedrevisions#Response
        example_response = {
            "query": {
                "alldeletedrevisions": [
                    {
                        "pageid": 0,
                        "revisions": [
                            {
                                "revid": 20151125,
                                "timestamp": "2015-11-25T00:00:00Z",
                                "comment": "c1",
                                "tags": ["t1"],
                            },
                            {
                                "revid": 20151124,
                                "timestamp": "2015-11-24T00:00:00Z",
                                "comment": "c2",
                                "tags": ["t1", "t2"],
                            }
                        ],
                        "ns": 0,
                        "title": "p1",
                    }
                ]
            }
        }
        pages = example_response['query']['alldeletedrevisions']
        mock_List().__iter__ = Mock(return_value=iter(pages))
        mock_List.generate_kwargs.side_effect = mwclient.listing.List.generate_kwargs
        wiki = Wiki()

        deleted_contributions = wiki.deleted_user_contributions('fred')
        items = list(deleted_contributions)

        args, kwargs = mock_List.call_args
        self.assertIsInstance(args[0], mwclient.Site)
        self.assertEqual(args[1:], ('alldeletedrevisions', 'adr'))
        self.assertEqual(kwargs, {'uselang': None,
                                  'adruser': 'fred',
                                  'adrprop': 'ids|title|timestamp|comment|flags|tags'})
        self.assertEqual(items, [
            WikiContrib(20151125, datetime(2015, 11, 25, tzinfo=timezone.utc),
                        'fred', 0, 'p1', 'c1', is_live=False, tags=["t1"]),
            WikiContrib(20151124, datetime(2015, 11, 24, tzinfo=timezone.utc),
                        'fred', 0, 'p1', 'c2', is_live=False, tags=["t1", "t2"])])


    @patch('wiki_interface.wiki.List')
    def test_deleted_user_contributions_with_multiple_pages(self, mock_List):
        # See https://www.mediawiki.org/wiki/API:Alldeletedrevisions#Response
        response = {
            "query": {
                "alldeletedrevisions": [
                    {
                        "pageid": 0,
                        "revisions": [
                            {
                                "revid": 20150102,
                                "timestamp": "2015-01-02T00:00:00Z",
                                "comment": "c01",
                                "tags": [],
                            },
                            {
                                "revid": 20150101,
                                "timestamp": "2015-01-01T00:00:00Z",
                                "comment": "c02",
                                "tags": [],
                            }
                        ],
                        "ns": 0,
                        "title": "p1",
                    },
                    {
                        "pageid": 1,
                        "revisions": [
                            {
                                "revid": 20160101,
                                "timestamp": "2016-01-01T00:00:00Z",
                                "comment": "c11",
                                "tags": [],
                            },
                            {
                                "revid": 20140101,
                                "timestamp": "2014-01-01T00:00:00Z",
                                "comment": "c12",
                                "tags": [],
                            }
                        ],
                        "ns": 0,
                        "title": "p2",
                    }
                ]
            }
        }
        pages = response['query']['alldeletedrevisions']
        mock_List().__iter__ = Mock(return_value=iter(pages))
        mock_List.generate_kwargs.side_effect = mwclient.listing.List.generate_kwargs
        wiki = Wiki()

        deleted_contributions = wiki.deleted_user_contributions('fred')
        items = list(deleted_contributions)

        args, kwargs = mock_List.call_args
        self.assertIsInstance(args[0], mwclient.Site)
        self.assertEqual(args[1:], ('alldeletedrevisions', 'adr'))
        self.assertEqual(kwargs, {'uselang': None,
                                  'adruser': 'fred',
                                  'adrprop': 'ids|title|timestamp|comment|flags|tags'})
        expected_items = [
            WikiContrib(20160101, datetime(2016, 1, 1, tzinfo=timezone.utc),
                        'fred', 0, 'p2', 'c11', is_live=False, tags=[]),
            WikiContrib(20150102, datetime(2015, 1, 2, tzinfo=timezone.utc),
                        'fred', 0, 'p1', 'c01', is_live=False, tags=[]),
            WikiContrib(20150101, datetime(2015, 1, 1, tzinfo=timezone.utc),
                        'fred', 0, 'p1', 'c02', is_live=False, tags=[]),
            WikiContrib(20140101, datetime(2014, 1, 1, tzinfo=timezone.utc),
                        'fred', 0, 'p2', 'c12', is_live=False, tags=[]),
            ]
        self.assertEqual(items, expected_items)


    @patch('wiki_interface.wiki.List')
    def test_deleted_user_contributions_with_permission_denied_exception(self, mock_List):
        mock_List().__iter__.side_effect = mwclient.errors.APIError('permissiondenied',
                                                                    'blah',
                                                                    'blah-blah')
        wiki = Wiki()

        deleted_contributions = wiki.deleted_user_contributions('fred')

        self.assertEqual(list(deleted_contributions), [])


    @patch('wiki_interface.wiki.List')
    def test_deleted_user_contributions_handles_hidden_comment(self, mock_List):
        # See https://www.mediawiki.org/wiki/API:Alldeletedrevisions#Response
        example_response = {
            "query": {
                "alldeletedrevisions": [
                    {
                        "pageid": 0,
                        "revisions": [
                            {
                                "revid": 999,
                                "timestamp": "2015-11-25T00:00:00Z",
                                "commenthidden": "",
                                "tags": ["t1"],
                            },
                        ],
                        "ns": 0,
                        "title": "p1",
                    }
                ]
            }
        }
        pages = example_response['query']['alldeletedrevisions']
        mock_List().__iter__ = Mock(return_value=iter(pages))
        mock_List.generate_kwargs.side_effect = mwclient.listing.List.generate_kwargs
        wiki = Wiki()

        deleted_contributions = wiki.deleted_user_contributions('fred')
        items = list(deleted_contributions)

        args, kwargs = mock_List.call_args
        self.assertIsInstance(args[0], mwclient.Site)
        self.assertEqual(args[1:], ('alldeletedrevisions', 'adr'))
        self.assertEqual(kwargs, {'uselang': None,
                                  'adruser': 'fred',
                                  'adrprop': 'ids|title|timestamp|comment|flags|tags'})
        self.assertEqual(items, [
            WikiContrib(999, datetime(2015, 11, 25, tzinfo=timezone.utc),
                        'fred', 0, 'p1', None, is_live=False, tags=["t1"]),
            ])


class UserBlocksTest(TestCase):
    # pylint: disable=invalid-name

    @patch('wiki_interface.wiki.logger')
    @patch('wiki_interface.wiki.Site')
    def test_user_blocks_with_no_blocks(self, mock_Site, mock_logger):
        mock_Site().logevents.return_value = iter([])
        wiki = Wiki()

        user_blocks = wiki.user_blocks('fred')

        self.assertEqual(user_blocks, [])
        mock_logger.error.assert_not_called()


    @patch('wiki_interface.wiki.logger')
    @patch('wiki_interface.wiki.Site')
    def test_user_blocks_with_multiple_events(self, mock_Site, mock_logger):
        jan_1 = '2020-01-01T00:00:00Z'
        feb_1 = '2020-02-01T00:00:00Z'
        mar_1 = '2020-03-01T00:00:00Z'
        apr_1 = '2020-04-01T00:00:00Z'
        may_1 = '2020-05-01T00:00:00Z'

        mock_Site().logevents.return_value = iter([
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(jan_1),
             'params': {'expiry': feb_1},
             'type': 'block',
             'action': 'block'},
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(mar_1),
             'params': {'expiry': apr_1},
             'type': 'block',
             'action': 'block'},
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(may_1),
             'params': {},
             'type': 'block',
             'action': 'unblock'}
            ])
        wiki = Wiki()

        user_blocks = wiki.user_blocks('fred')

        self.assertEqual(user_blocks, [BlockEvent('fred', isoparse(jan_1), isoparse(feb_1)),
                                       BlockEvent('fred', isoparse(mar_1), isoparse(apr_1)),
                                       UnblockEvent('fred', isoparse(may_1))])
        mock_logger.error.assert_not_called()


    @patch('wiki_interface.wiki.logger')
    @patch('wiki_interface.wiki.Site')
    def test_user_blocks_with_reblock(self, mock_Site, mock_logger):
        jan_1 = '2020-01-01T00:00:00Z'
        jan_2 = '2020-01-02T00:00:00Z'
        feb_1 = '2020-02-01T00:00:00Z'
        mar_1 = '2020-03-01T00:00:00Z'

        mock_Site().logevents.return_value = iter([
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(jan_1),
             'params': {'expiry': feb_1},
             'type': 'block',
             'action': 'block'},
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(jan_2),
             'params': {'expiry': mar_1},
             'type': 'block',
             'action': 'reblock'},
        ])
        wiki = Wiki()

        user_blocks = wiki.user_blocks('fred')

        self.assertEqual(user_blocks, [BlockEvent('fred', isoparse(jan_1), isoparse(feb_1)),
                                       BlockEvent('fred', isoparse(jan_2), isoparse(mar_1),
                                                  is_reblock=True)])
        mock_logger.error.assert_not_called()


    @patch('wiki_interface.wiki.logger')
    @patch('wiki_interface.wiki.Site')
    def test_user_blocks_with_unknown_action(self, mock_Site, mock_logger):
        jan_1 = '2020-01-01T00:00:00Z'
        feb_1 = '2020-02-01T00:00:00Z'
        mar_1 = '2020-03-01T00:00:00Z'
        apr_1 = '2020-04-01T00:00:00Z'

        mock_Site().logevents.return_value = iter([
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(jan_1),
             'params': {'expiry': feb_1},
             'type': 'block',
             'action': 'wugga-wugga'},
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(mar_1),
             'params': {'expiry': apr_1},
             'type': 'block',
             'action': 'block'},
        ])
        wiki = Wiki()

        user_blocks = wiki.user_blocks('fred')

        self.assertEqual(user_blocks, [BlockEvent('fred', isoparse(mar_1), isoparse(apr_1))])
        mock_logger.error.assert_called_once()


class MultiUserBlocksTest(TestCase):
    #pylint: disable=invalid-name

    def test_multi_user_blocks_with_no_users_returns_empty_list(self):
        wiki = Wiki()

        blocks = async_to_sync(wiki.multi_user_blocks)([])

        self.assertEqual(blocks, [])


    @patch('wiki_interface.wiki.Site')
    def test_multi_user_blocks_with_one_user_and_no_blocks_returns_empty_list(self, mock_Site):
        mock_Site().logevents.return_value = []
        wiki = Wiki()

        blocks = async_to_sync(wiki.multi_user_blocks)(['fred'])

        self.assertEqual(blocks, [])
        mock_Site().logevents.assert_called_once_with(title='User:fred', type='block')


    @patch('wiki_interface.wiki.Site')
    def test_multi_user_blocks_with_one_user_and_multiple_blocks_returns_correct_list(self, mock_Site):
        jan_1 = '2020-01-01T00:00:00Z'
        feb_1 = '2020-02-01T00:00:00Z'
        mar_1 = '2020-03-01T00:00:00Z'
        apr_1 = '2020-04-01T00:00:00Z'
        mock_Site().logevents.return_value = iter([
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(mar_1),
             'params': {'expiry': apr_1},
             'type': 'block',
             'action': 'block'},
            {'title': 'User:fred',
             'timestamp': mwclient.util.parse_timestamp(jan_1),
             'params': {'expiry': feb_1},
             'type': 'block',
             'action': 'block'},
            ])
        wiki = Wiki()

        blocks = async_to_sync(wiki.multi_user_blocks)(['fred'])

        self.assertEqual(blocks, [
            BlockEvent('fred', isoparse(mar_1), isoparse(apr_1)),
            BlockEvent('fred', isoparse(jan_1), isoparse(feb_1)),
        ])
        mock_Site().logevents.assert_called_once_with(title='User:fred', type='block')


    @patch('wiki_interface.wiki.Site')
    def test_multi_user_blocks_with_two_user_and_one_block_each_returns_correct_list(self, mock_Site):
        jan_1 = '2020-01-01T00:00:00Z'
        feb_1 = '2020-02-01T00:00:00Z'
        mar_1 = '2020-03-01T00:00:00Z'
        apr_1 = '2020-04-01T00:00:00Z'
        logevents_data = {
            'User:fred': [
                {'title': 'User:fred',
                 'timestamp': mwclient.util.parse_timestamp(jan_1),
                 'params': {'expiry': feb_1},
                 'type': 'block',
                 'action': 'block'},
            ],
            'User:wilma': [
                {'title': 'User:wilma',
                 'timestamp': mwclient.util.parse_timestamp(mar_1),
                 'params': {'expiry': apr_1},
                 'type': 'block',
                 'action': 'block'},
            ],
        }
        mock_Site().logevents.side_effect = lambda title, type: logevents_data[title]
        wiki = Wiki()

        blocks = async_to_sync(wiki.multi_user_blocks)(['fred', 'wilma'])

        mock_Site().logevents.assert_has_calls([call(title='User:fred', type='block'),
                                                call(title='User:wilma', type='block')])
        self.assertEqual(blocks, [
            BlockEvent('wilma', isoparse(mar_1), isoparse(apr_1)),
            BlockEvent('fred', isoparse(jan_1), isoparse(feb_1)),
        ])


    @patch('wiki_interface.wiki.Site')
    def test_multi_user_blocks_with_two_user_and_multiple_blocks_each_returns_correct_list(self, mock_Site):
        jan_1 = '2020-01-01T00:00:00Z'
        feb_1 = '2020-02-01T00:00:00Z'
        mar_1 = '2020-03-01T00:00:00Z'
        apr_1 = '2020-04-01T00:00:00Z'
        may_1 = '2020-05-01T00:00:00Z'
        jun_1 = '2020-06-01T00:00:00Z'
        jul_1 = '2020-07-01T00:00:00Z'
        aug_1 = '2020-08-01T00:00:00Z'
        logevents_data = {
            'User:fred': [
                {'title': 'User:fred',
                 'timestamp': mwclient.util.parse_timestamp(jul_1),
                 'params': {'expiry': aug_1},
                 'type': 'block',
                 'action': 'block'},
                {'title': 'User:fred',
                 'timestamp': mwclient.util.parse_timestamp(jan_1),
                 'params': {'expiry': feb_1},
                 'type': 'block',
                 'action': 'block'},
            ],
            'User:wilma': [
                {'title': 'User:wilma',
                 'timestamp': mwclient.util.parse_timestamp(may_1),
                 'params': {'expiry': jun_1},
                 'type': 'block',
                 'action': 'block'},
                {'title': 'User:wilma',
                 'timestamp': mwclient.util.parse_timestamp(mar_1),
                 'params': {'expiry': apr_1},
                 'type': 'block',
                 'action': 'block'},
            ],
        }
        mock_Site().logevents.side_effect = lambda title, type: logevents_data[title]
        wiki = Wiki()

        blocks = async_to_sync(wiki.multi_user_blocks)(['fred', 'wilma'])

        mock_Site().logevents.assert_has_calls([call(title='User:fred', type='block'),
                                                call(title='User:wilma', type='block')])
        self.assertEqual(blocks, [
            BlockEvent('fred', isoparse(jul_1), isoparse(aug_1)),
            BlockEvent('wilma', isoparse(may_1), isoparse(jun_1)),
            BlockEvent('wilma', isoparse(mar_1), isoparse(apr_1)),
            BlockEvent('fred', isoparse(jan_1), isoparse(feb_1)),
        ])


class UserLogsTest(TestCase):
    # pylint: disable=invalid-name

    @patch('wiki_interface.wiki.Site')
    def test_user_log_events(self, mock_Site):
        mock_Site().logevents.return_value = iter([
            {
                'title': 'Fred-sock',
                'params': {'userid': 37950265},
                'type': 'newusers',
                'action': 'create2',
                'user': 'Fred',
                'timestamp': (2019, 11, 29, 0, 0, 0, 0, 0, 0),
                'comment': 'testing',
            }
        ])
        wiki = Wiki()

        log_events = list(wiki.user_log_events('Fred'))
        self.assertEqual(log_events, [LogEvent(
            datetime(2019, 11, 29, tzinfo=timezone.utc),
            'Fred',
            'Fred-sock',
            'newusers',
            'create2',
            'testing')])


    @patch('wiki_interface.wiki.Site')
    def test_user_log_events_handles_hidden_comment(self, mock_Site):
        mock_Site().logevents.return_value = iter([
            {
                'title': 'Fred-sock',
                'params': {'userid': 37950265},
                'type': 'newusers',
                'action': 'create2',
                'user': 'Fred',
                'timestamp': (2019, 11, 29, 0, 0, 0, 0, 0, 0),
                'commenthidden': '',
            }
        ])
        wiki = Wiki()

        log_events = list(wiki.user_log_events('Fred'))
        self.assertEqual(log_events, [LogEvent(
            datetime(2019, 11, 29, tzinfo=timezone.utc),
            'Fred',
            'Fred-sock',
            'newusers',
            'create2',
            None)])


    @patch('wiki_interface.wiki.Site')
    def test_user_log_events_handles_hidden_title(self, mock_Site):
        mock_Site().logevents.return_value = iter([
            {
                'params': {'userid': 37950265},
                'type': 'newusers',
                'action': 'create2',
                'user': 'Fred',
                'timestamp': (2019, 11, 29, 0, 0, 0, 0, 0, 0),
                'commenthidden': '',
            }
        ])
        wiki = Wiki()

        log_events = list(wiki.user_log_events('Fred'))
        self.assertEqual(log_events, [LogEvent(
            datetime(2019, 11, 29, tzinfo=timezone.utc),
            'Fred',
            None,
            'newusers',
            'create2',
            None)])


    @patch('wiki_interface.wiki.Site')
    def test_user_log_events_handles_hidden_action(self, mock_Site):
        mock_Site().logevents.return_value = iter([
            {
                'title': 'Fred-sock',
                'params': {'userid': 37950265},
                'type': 'newusers',
                'user': 'Fred',
                'timestamp': (2019, 11, 29, 0, 0, 0, 0, 0, 0),
                'commenthidden': '',
            }
        ])
        wiki = Wiki()

        log_events = list(wiki.user_log_events('Fred'))
        self.assertEqual(log_events, [LogEvent(
            datetime(2019, 11, 29, tzinfo=timezone.utc),
            'Fred',
            'Fred-sock',
            'newusers',
            None,
            None)])


class GetPageTest(TestCase):
    #pylint: disable=invalid-name

    def test_page(self):
        wiki = Wiki()
        page = wiki.page('foo')

        self.assertIsInstance(page, Page)


class PageTest(TestCase):
    #pylint: disable=invalid-name

    def test_construct(self):
        wiki = Wiki()
        page = Page(wiki, "my page")

        self.assertEqual(page.wiki, wiki)
        self.assertIsNotNone(page.mw_page)


    @patch('wiki_interface.wiki.Site')
    def test_exists_true(self, mock_Site):
        mock_Site().pages.__getitem__().exists = True
        wiki = Wiki()
        page = Page(wiki, "my page")

        self.assertTrue(page.exists())


    @patch('wiki_interface.wiki.Site')
    def test_exists_false(self, mock_Site):
        mock_Site().pages.__getitem__().exists = False
        wiki = Wiki()
        page = Page(wiki, "my page")

        self.assertFalse(page.exists())


    @patch('wiki_interface.wiki.Site')
    def test_revisions(self, mock_Site):
        mock_Site().pages.__getitem__().revisions.return_value = [
            {'revid': 101, 'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0), 'user': 'fred', 'comment': 'c1'},
            {'revid': 102, 'timestamp': (2020, 7, 29, 0, 0, 0, 0, 0, 0), 'user': 'fred', 'comment': 'c2'}]
        mock_Site().pages.__getitem__().name = 'blah'
        mock_Site().pages.__getitem__().namespace = 0
        wiki = Wiki()

        revisions = list(wiki.page('blah').revisions())

        self.assertIsInstance(revisions[0], WikiContrib)
        self.assertEqual(revisions, [
            WikiContrib(101, datetime(2020, 7, 30, tzinfo=timezone.utc), 'fred', 0, 'blah', 'c1'),
            WikiContrib(102, datetime(2020, 7, 29, tzinfo=timezone.utc), 'fred', 0, 'blah', 'c2')])


    @patch('wiki_interface.wiki.Site')
    def test_revisions_with_hidden_comment(self, mock_Site):
        mock_Site().pages.__getitem__().revisions.return_value = [
            {'revid': 100, 'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0), 'user': 'fred', 'commenthidden': ''}]
        mock_Site().pages.__getitem__().name = 'blah'
        mock_Site().pages.__getitem__().namespace = 0
        wiki = Wiki()

        revisions = list(wiki.page('blah').revisions())

        self.assertIsInstance(revisions[0], WikiContrib)
        self.assertEqual(revisions, [
            WikiContrib(100, datetime(2020, 7, 30, tzinfo=timezone.utc), 'fred', 0, 'blah', None)
        ])


    @patch('wiki_interface.wiki.Site')
    def test_revisions_with_count(self, mock_Site):
        mock_Site().pages.__getitem__().revisions.return_value = [
            {'revid': 20200730, 'timestamp': (2020, 7, 30, 0, 0, 0, 0, 0, 0), 'user': 'fred', 'comment': 'c1'},
            {'revid': 20200729, 'timestamp': (2020, 7, 29, 0, 0, 0, 0, 0, 0), 'user': 'fred', 'comment': 'c2'}]
        mock_Site().pages.__getitem__().name = 'blah'
        mock_Site().pages.__getitem__().namespace = 0
        wiki = Wiki()

        revisions = list(wiki.page('blah').revisions(count=1))

        self.assertEqual(revisions,
                         [WikiContrib(20200730, datetime(2020, 7, 30, tzinfo=timezone.utc), 'fred', 0, 'blah', 'c1')])


class IsValidUsernameTest(TestCase):
    #pylint: disable=invalid-name

    @patch('wiki_interface.wiki.Site')
    def test_with_valid_name(self, mock_Site):
        mock_Site().usercontributions.return_value = []
        wiki = Wiki()

        self.assertTrue(wiki.is_valid_username('foo'))
        mock_Site().usercontributions.assert_called_once_with('foo', limit=1)


    @patch('wiki_interface.wiki.Site')
    def test_with_invalid_name(self, mock_Site):
        mock_Site().usercontributions.side_effect = mwclient.errors.APIError('baduser',
                                                                             'blah',
                                                                             None)
        wiki = Wiki()

        self.assertFalse(wiki.is_valid_username('foo'))
        mock_Site().usercontributions.assert_called_once_with('foo', limit=1)


    @patch('wiki_interface.wiki.Site')
    def test_with_unexpected_exception(self, mock_Site):
        mock_Site().usercontributions.side_effect = RuntimeError('blah')
        wiki = Wiki()

        with self.assertRaises(RuntimeError):
            wiki.is_valid_username('foo')
        mock_Site().usercontributions.assert_called_once_with('foo', limit=1)
