# -*- coding: utf-8 -*-

# Copyright(C) 2013      Laurent Bachelier
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.


from weboob.deprecated.browser import Browser, BrowserIncorrectPassword
from .pages import LoginPage, AccountPage, DownloadHistoryPage, LastDownloadHistoryPage, SubmitPage, HistoryParser, UselessPage, HistoryPage, CSVAlreadyAsked
from .newpages import NewHomePage, NewAccountPage, NewProHistoryPage, NewPartHistoryPage
import datetime


__all__ = ['Paypal']


class Paypal(Browser):
    DOMAIN = 'www.paypal.com'
    PROTOCOL = 'https'
    CERTHASH = ['b8f6c76050ed3035aab08474b1da0ff783f20d114b1740e8db275fe433ff69af', '96753399cf183334cef00a72719ea8e13cfe68d1e953006348f41f884180de15']
    ENCODING = 'UTF-8'
    PAGES = {
        '/cgi-bin/webscr\?cmd=_login-run$':             LoginPage,
        '/cgi-bin/webscr\?cmd=_login-submit.+$':        LoginPage,  # wrong login
        '/cgi-bin/webscr\?cmd=_login-processing.+$':    UselessPage,
        '/cgi-bin/webscr\?cmd=_account&nav=0.0$':  AccountPage,
        '/cgi-bin/webscr\?cmd=_history-download&nav=0.3.1$':  DownloadHistoryPage,
        '/cgi-bin/webscr\?cmd=_history&nav=0.3.0$':  HistoryPage,
        '/cgi-bin/webscr\?cmd=_history&dispatch=[a-z0-9]+$':  HistoryPage,
        '/cgi-bin/webscr\?cmd=_history-download-recent$': LastDownloadHistoryPage,
        '/cgi-bin/webscr\?dispatch=[a-z0-9]+$': (SubmitPage, HistoryParser()),
        '/cgi-bin/webscr\?cmd=_history-download-recent-submit&dispatch=[a-z0-9]+$': (SubmitPage, HistoryParser()),
        'https://www.paypal.com/webapps/business/\?nav=0.0': NewHomePage,
        'https://www.paypal.com/businessexp/money': NewAccountPage,
        'https://www.paypal.com/webapps/business/activity\?.*': NewProHistoryPage,
        'https://www.paypal.com/myaccount/activity/.*': (NewPartHistoryPage, 'json'),
        'https://www.paypal.com/myaccount/': NewProHistoryPage,
    }

    DEFAULT_TIMEOUT = 30  # CSV export is slow

    BEGINNING = datetime.date(1998,6,1) # The day PayPal was founded
    website = None

    def find_website_version(self):
        self.location('/en/cgi-bin/webscr?cmd=_account&nav=0.0')
        if self.is_on_page(AccountPage):
            self.website = "old"
        else:
            self.website = "new"
            self.location('/webapps/business/?nav=0.0')
            if self.is_on_page(NewHomePage):
                self.account_type = "pro"
            else:
                self.account_type = "perso"

    def home(self):
        self.location('https://' + self.DOMAIN + '/en/cgi-bin/webscr?cmd=_login-run')

    def is_logged(self):
        # TODO Does not handle disconnect mid-session
        return not self.is_on_page(LoginPage)

    def login(self):
        assert isinstance(self.username, basestring)
        assert isinstance(self.password, basestring)

        if not self.is_on_page(LoginPage):
            self.location('https://' + self.DOMAIN + '/en/cgi-bin/webscr?cmd=_login-run')

        self.page.login(self.username, self.password)

        if self.is_on_page(LoginPage):
            raise BrowserIncorrectPassword()

        self.find_website_version()

    def get_accounts(self):
        if self.website == "old":
            if not self.is_on_page(AccountPage):
                self.location('/en/cgi-bin/webscr?cmd=_account&nav=0.0')
        elif not self.is_on_page(NewAccountPage):
            self.location('/businessexp/money')

        return self.page.get_accounts()

    def get_account(self, _id):
        if self.website == "old":
            if not self.is_on_page(AccountPage):
                self.location('/en/cgi-bin/webscr?cmd=_account&nav=0.0')
        elif not self.is_on_page(NewAccountPage):
            self.location('/businessexp/money')

        return self.page.get_account(_id)

    def get_history(self, account, step_min=90, step_max=365*10):
        def fetch_fn(start, end):
            def transactions():
                parse = True
                while parse:
                    for trans in self.page.iter_transactions(account):
                        yield trans
                    parse = self.page.next()
            self.history(start=start, end=end)
            if next(self.page.parse(), False):
                return transactions()
        return self.smart_fetch(beginning=self.BEGINNING,
                                end=datetime.date.today(),
                                step_min=step_min,
                                step_max=step_max,
                                fetch_fn=fetch_fn)

    def history(self, start, end):
        self.location('/en/cgi-bin/webscr?cmd=_history&nav=0.3.0')
        self.page.filter(start, end)
        assert self.is_on_page(HistoryPage)

    def get_download_history(self, account, step_min=None, step_max=None):
        if step_min is None and step_max is None:
            if self.website == "old":
                step_min = 90
                step_max = 365*2
            else:
                step_min = 90
                step_max = 180
        def fetch_fn(start, end):
            if self.website == "old" and self.download_history(start, end).rows:
                return self.page.iter_transactions(account)
            elif self.download_history(start, end):
                return self.page.iter_transactions(account)
        assert step_max <= 365*2 # PayPal limitations as of 2014-06-16
        try:
            for i in self.smart_fetch(beginning=self.BEGINNING,
                                end=datetime.date.today(),
                                step_min=step_min,
                                step_max=step_max,
                                fetch_fn=fetch_fn):
                yield i
        except CSVAlreadyAsked:
            for i in self.download_last_history(account):
                yield i

    def smart_fetch(self, beginning, end, step_min, step_max, fetch_fn):
        """
        Fetches transactions in small chunks to avoid request timeouts.
        Time period of each requested chunk is adjusted dynamically.
        """
        FACTOR = 2
        step = step_min
        while end > beginning:
            start = end - datetime.timedelta(step)
            chunk = fetch_fn(start, end)
            end = start - datetime.timedelta(1)
            if chunk:
                # If there're transactions in current period,
                # decrease the period.
                step = max(step_min, step/FACTOR)
                for trans in chunk:
                    yield trans
            else:
                # If there's no transactions in current period,
                # increase the period.
                step = min(step_max, step*FACTOR)

    def download_history(self, start, end):
        """
        Download CSV history.
        However, it is not normalized, and sometimes the download is refused
        and sent later by mail.
        """
        if self.website == "old":
            self.location('/en/cgi-bin/webscr?cmd=_history-download&nav=0.3.1')
            assert self.is_on_page(DownloadHistoryPage)
            self.page.download(start, end)
            assert self.is_on_page(SubmitPage)
            return self.page.document
        else:
            s = start.strftime('%d/%m/%Y')
            e = end.strftime('%d/%m/%Y')
            #Settings a big magic number so we get all transaction for the period
            LIMIT = '9999'
            if self.account_type == "pro":
                self.location('/webapps/business/activity?fromdate=' + s + '&todate=' + e + '&transactiontype=ALL_TRANSACTIONS&currency=ALL_TRANSACTIONS_CURRENCY&limit=' + LIMIT)
            else:
                self.location('/myaccount/activity/filter?start=' + s + '&end=' + e + '&limit=' + LIMIT)
            return self.page.transaction_left()

    def download_last_history(self, account):
        self.location('/en/cgi-bin/webscr?cmd=_history-download-recent')
        self.page.download()
        if self.page.document.rows:
            return self.page.iter_transactions(account)

    def transfer(self, from_id, to_id, amount, reason=None):
        raise NotImplementedError()
