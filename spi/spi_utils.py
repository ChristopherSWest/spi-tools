import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

from mwparserfromhell import parse
from mwparserfromhell.wikicode import Wikicode


class ArchiveError(ValueError):
    pass

class InvalidIpV4Error(ValueError):
    pass


class SpiDocumentBase:
    def master_name(self):
        parts = self.page_title.split('/')
        if parts[-1] == 'Archive':
            parts.pop()
        return parts[-1]


@dataclass(frozen=True)
class SpiSourceDocument(SpiDocumentBase):
    wikitext: str
    page_title: str


@dataclass(frozen=True)
class SpiParsedDocument(SpiDocumentBase):
    wikicode: Wikicode
    page_title: str


class SpiCase:
    def __init__(self, *sources):
        """A case can be made up of multiple source documents.  In practice,
        there will usually be two; the currently active page, and the
        archive page.  New cases, however, may not have an archive
        yet, and in exceptional cases, there may be multiple archives.

        Each source is SpiSourceDocument.
        """
        self.parsed_docs = [SpiParsedDocument(parse(s.wikitext), s.page_title)
                            for s in sources]

        master_names = set(doc.master_name() for doc in self.parsed_docs)
        if len(master_names) == 0:
            raise ArchiveError("No sockmaster name found")
        if len(master_names) > 1:
            raise ArchiveError("Multiple sockmaster names found: %s" % master_names)
        self._master_name = master_names.pop()


    def master_name(self):
        return self._master_name


    def days(self):
        """Return an iterable of SpiCaseDays"""
        for doc in self.parsed_docs:
            for section in doc.wikicode.get_sections(levels=[3]):
                yield SpiCaseDay(section, doc.page_title)


    def find_all_ips(self):
        '''Iterates over all the IPs mentioned in checkuser templates.
        Each user is represented as a SpiIpInfo.  Order of iteration
        is not guaranteed, and templates are not deduplicated.
        '''
        for day in self.days():
            for ip_address in day.find_ips():
                yield ip_address


    def find_all_users(self):
        '''Iterates over all the users mentioned in checkuser templates.
        Each user is represented as a SpiUserInfo.  Order of iteration
        is not guaranteed, and templates are not deduplicated.

        The master is included as a user, with date set to None.

        '''
        yield SpiUserInfo(self.master_name(), None)
        for day in self.days():
            for user in day.find_users():
                yield user


class SpiCaseDay:
    def __init__(self, wikicode, page_title):
        self.wikicode = wikicode
        self.page_title = page_title


    def date(self):
        headings = self.wikicode.filter_headings(matches=lambda h: h.level == 3)
        h3_count = len(headings)
        if h3_count == 1:
            return headings[0].title
        raise ArchiveError("Expected exactly 1 level-3 heading, found %d" % h3_count)


    def find_users(self):
        '''Iterates over all the accounts mentioned in checkuser templates.
        Each user is represented as an SpiUserInfo.  Order of iteration
        is not guaranteed, and templates are not deduplicated.

        '''
        date = self.date()
        templates = self.wikicode.filter_templates(
            matches=lambda n: n.name.matches(['checkuser',
                                              'user',
                                              'SPIarchive notice']))
        for template in templates:
            username = template.get('1').value
            yield SpiUserInfo(str(username), str(date))

    def find_unique_users(self):
        '''Iterates over all the unique accounts mentioned in checkuser
        templates.  Each user is represented as an SpiUserInfo.  Order
        of iteration is not guaranteed, but unlike find_users(),
        templates are deduplicated.

        '''
        seen = set()
        for user in self.find_users():
            if user not in seen:
                seen.add(user)
                yield user


    def find_ips(self):
        '''Iterates over all the IPs mentioned in checkuser templates.
        Each ip is represented as an SpiIpInfo.  Order of iteration
        is not guaranteed, and templates are not deduplicated.
        '''
        date = self.date()
        templates = self.wikicode.filter_templates(
            matches=lambda n: n.name.matches('checkip'))
        for template in templates:
            ip_address = template.get('1').value
            try:
                yield SpiIpInfo(str(ip_address), str(date), self.page_title)
            except InvalidIpV4Error:
                pass


@dataclass(order=True, unsafe_hash=True)
class SpiUserInfo:
    username: str
    date: str


@dataclass(order=True, unsafe_hash=True)
class SpiIpInfo:
    ip: str
    date: str
    page_title: str

    def __init__(self, ip_str, date, page_title):
        try:
            self.ip = IPv4Address(ip_str)
        except ValueError as error:
            raise InvalidIpV4Error(str(error))
        self.date = date
        self.page_title = page_title


    @staticmethod
    def find_common_network(infos):
        ips = [int(i.ip) for i in infos]
        bits = [list(map(int, format(i, '032b'))) for i in ips]
        slices = zip(*bits)
        bit_sets = [set(s) for s in slices]
        prefix = 0
        prefix_length = 0
        done = False
        for bit_set in bit_sets:
            prefix <<= 1
            if done:
                continue
            if len(bit_set) > 1:
                done = True
                continue
            prefix_length += 1
            prefix |= bit_set.pop()
        return IPv4Network((prefix, prefix_length))
