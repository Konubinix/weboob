# -*- coding: utf-8 -*-

# Copyright(C) 2014      Samuel Loury
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


from weboob.browser2 import LoginBrowser, URL

from .pages import LoginPage, PDFList
from weboob.browser2.page import need_login


class VirginBrowser(LoginBrowser):
    BASEURL = 'https://espaceclient.virginmobile.fr'

    login = URL('/$', LoginPage)
    pdf_list_page = URL('/mobile/Mobile/Mes-factures', PDFList)

    def __init__(self, *args, **kwargs):
        self.logged_in = False
        return super(VirginBrowser, self).__init__(*args, **kwargs)

    def do_login(self):
        if self.logged_in:
            return
        self.login.stay_or_go()
        res = self.page.login(self.username,
                              self.password)
        if res.status_code != 200:
            raise BrowserIncorrectPassword(self.page.get_error())
        self.logged_in = True

    @need_login
    def iter_bills(self, subscription):
        self.pdf_list_page.stay_or_go()
        return self.page.iter_bills(subscription)
