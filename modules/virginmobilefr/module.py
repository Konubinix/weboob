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


from weboob.tools.backend import Module, BackendConfig
from weboob.tools.value import ValueBackendPassword, ValueBool

from weboob.capabilities.bill import CapBill, Subscription, BillNotFound
from weboob.capabilities.base import find_object

from .browser import VirginBrowser

__all__ = ['VirginModule']


class VirginModule(Module, CapBill):
    NAME = 'virginmobilefr'
    DESCRIPTION = u'French version of the virgin mobile website.'
    MAINTAINER = u'Samuel Loury'
    EMAIL = 'konubinixweb@gmail.fr'
    LICENSE = 'AGPLv3+'
    VERSION = '1.0'

    BROWSER = VirginBrowser
    CONFIG = BackendConfig(ValueBackendPassword('login',
                                                label='Identifiant',
                                                masked=False),
                           ValueBackendPassword('password',
                                                label='Password',
                                                masked=True)
                           )

    def create_default_browser(self):
      return self.create_browser(username=self.config['login'].get(),
                                 password=self.config['password'].get())

    def download_bill(self, id):
        """
        Download a bill.

        :param id: ID of bill
        :rtype: str
        :raises: :class:`BillNotFound`
        """
        bill = self.get_bill(id)
        res = self.browser.open(bill._url)
        return res.text.encode("utf-8")

    def get_bill(self, id):
        """
        Get a bill.

        :param id: ID of bill
        :rtype: :class:`Bill`
        :raises: :class:`BillNotFound`
        """
        return find_object(
            self.iter_bills(self.iter_subscription()[0]),
            id=id,
            error=BillNotFound)

    def get_subscription(self, _id):
        """
        Get a subscription.

        :param _id: ID of subscription
        :rtype: :class:`Subscription`
        :raises: :class:`SubscriptionNotFound`
        """
        return Subscription(self.config['login'].get())

    def iter_bills(self, subscription):
        """
        Iter bills.

        :param subscription: subscription to get bills
        :type subscription: :class:`Subscription`
        :rtype: iter[:class:`Bill`]
        """
        return self.browser.iter_bills(subscription)

    def iter_subscription(self):
        """
        Iter subscriptions.

        :rtype: iter[:class:`Subscription`]
        """
        return [Subscription(self.config['login'].get()),]
