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


from weboob.browser2 import HTMLPage
from weboob.capabilities.bill import Bill
import datetime
from re import sub
from decimal import Decimal

class LoginPage(HTMLPage):
    def login(self, username, password):
        form = self.get_form(xpath='//form')
        form['login'] = username
        form['pwd'] = password
        return form.submit()

    @property
    def logged(self):
      try:
        self.get_form(xpath='//form')
        return False
      except FormNotFound:
        return True

class PDFList(HTMLPage):
    def iter_bills(self, subscription):
        for el in self.doc.xpath('//a[@class="vm-download"]'):
            href = el.attrib['href'].decode("utf-8")
            datestr = [text for text in el.itertext()][-1].decode(self.doc.docinfo.encoding)
            bill = Bill()
            bill.date = datetime.datetime.strptime(
                datestr, "%Y-%m-%d")
            bill.id = datestr
            bill.format = u"pdf"
            bill.label = datestr
            if type(subscription) == unicode:
                bill.idparent = subscription
            else:
                bill.idparent = subscription.id
            price_raw = el.getparent().getnext().getnext().getchildren()[0].text
            bill.price = Decimal(sub(r'[^\d.]', '', price_raw))
            bill.currency = sub(r'[\d.]', '', price_raw)
            bill._url = href
            yield bill
