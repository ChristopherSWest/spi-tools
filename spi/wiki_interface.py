"""A high-level programatic interface to the wiki.

This sits on top of mwclient.Site and provides a higher level
abstraction.  Sets of values are passed as iterators instead of piped
strings.  Times are represented as datetimes instead of struct_times.
Future functionality may include caching.

All wiki access should go through this layer.  Do not use
mwclient.Site directly.

"""
import logging

import django.contrib.auth
from django.conf import settings
from mwclient import Site
import mwparserfromhell

from .spi_utils import SpiSourceDocument, SpiCase

logger = logging.getLogger('wiki_interface')

class Wiki:
    """High-level wiki interface.

    This knows about user credentials, so you must Create a new
    instance of this for every request.

    """
    def __init__(self, request=None):
        self.site = self.get_mw_site(request)


    @staticmethod
    def get_mw_site(request):
        user = request and django.contrib.auth.get_user(request)

        # It's not clear if we need to bother checking to see if the user
        # is authenticated.  Maybe with an AnonymousUser, everything just
        # works?  If so, these two code paths could be merged.
        if user is None or user.is_anonymous:
            auth_info = {}
        else:
            access_token = (user
                            .social_auth
                            .get(provider='mediawiki')
                            .extra_data['access_token'])
            auth_info = {
                'consumer_token': settings.SOCIAL_AUTH_MEDIAWIKI_KEY,
                'consumer_secret': settings.SOCIAL_AUTH_MEDIAWIKI_SECRET,
                'access_token': access_token['oauth_token'],
                'access_secret': access_token['oauth_token_secret']
            }

        return Site(settings.MEDIAWIKI_SITE_NAME,
                    clients_useragent=settings.MEDIAWIKI_USER_AGENT,
                    **auth_info)


    def get_current_case_names(self):
        """Return an list of the currently active SPI case names as strings.

        """
        overview = self.site.pages['Wikipedia:Sockpuppet investigations/Cases/Overview'].text()
        wikicode = mwparserfromhell.parse(overview)
        templates = wikicode.filter_templates(matches=lambda n: n.name.matches('SPIstatusentry'))
        return [str(t.get(1)) for t in templates]


    def page_exists(self, title):
        """Return True if the page exists, False otherwise."""

        return self.site.pages[title].exists


    def get_case_ips(self, case_name):
        """Get all the IP addresses which have been mentioned
        in a SPI case.

        Returns a iterable over SpiIpInfos

        """
        case_title = 'Wikipedia:Sockpuppet investigations/%s' % case_name
        archive_title = '%s/Archive' % case_title

        case_doc = SpiSourceDocument(case_title, self.site.pages[case_title].text())
        docs = [case_doc]

        archive_text = self.site.pages[archive_title].text()
        if archive_text:
            archive_doc = SpiSourceDocument(archive_title, archive_text)
            docs.append(archive_doc)

        case = SpiCase(*docs)
        return case.find_all_ips()



    def get_registration_time(self, user):
        """Return the registration time for a user as a string.

        If the registration time can't be determined, returns None.

        """
        registrations = self.site.users(users=[user], prop=['registration'])
        userinfo = registrations.next()
        try:
            return userinfo['registration']
        except KeyError:
            return None


    def get_case(self, master_name, use_archive=True):
        """Returns a SpiCase.

        If use_archive is true, both the current case and any existing
        archive is used.  Otherwise, just the current case.

        """
        case_title = 'Wikipedia:Sockpuppet investigations/%s' % master_name
        archive_title = '%s/Archive' % case_title

        case_doc = SpiSourceDocument(case_title, self.site.pages[case_title].text())
        docs = [case_doc]

        archive_text = use_archive and self.site.pages[archive_title].text()
        if archive_text:
            archive_doc = SpiSourceDocument(archive_title, archive_text)
            docs.append(archive_doc)

        return SpiCase(*docs)
