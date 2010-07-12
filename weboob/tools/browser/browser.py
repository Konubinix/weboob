# -*- coding: utf-8 -*-

# Copyright(C) 2010  Romain Bignon
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.


import mechanize
import urllib
import urllib2
try:
    from mechanize import ControlNotFoundError
except ImportError:
    from ClientForm import ControlNotFoundError
import re
import time
from logging import warning, debug
from copy import copy
from threading import RLock

from weboob.tools.parsers import get_parser
from weboob.tools.decorators import retry

# Try to load cookies
try:
    from weboob.tools.firefox_cookies import FirefoxCookieJar
except ImportError, e:
    warning("Unable to store cookies: %s" % e)
    HAVE_COOKIES = False
else:
    HAVE_COOKIES = True


__all__ = ['BrowserIncorrectPassword', 'BrowserBanned', 'BrowserUnavailable', 'BrowserRetry',
           'BasePage', 'BaseBrowser', 'ExpectedElementNotFound']


# Exceptions
class BrowserIncorrectPassword(Exception):
    pass


class BrowserBanned(BrowserIncorrectPassword):
    pass


class BrowserUnavailable(Exception):
    pass


class BrowserRetry(Exception):
    pass


class ExpectedElementNotFound(Exception):
    pass


class NoHistory(object):
    """
    We don't want to fill memory with history
    """
    def __init__(self):
        pass

    def add(self, request, response):
        pass

    def back(self, n, _response):
        pass

    def clear(self):
        pass

    def close(self):
        pass


class BasePage(object):
    """
    Base page
    """
    def __init__(self, browser, document, url='', groups=None, group_dict=None):
        self.browser = browser
        self.document = document
        self.url = url
        self.groups = groups
        self.group_dict = group_dict

    def on_loaded(self):
        """
        Called when the page is loaded.
        """
        pass

class BaseBrowser(mechanize.Browser):
    """
    Base browser class to navigate on a website.
    """

    # ------ Class attributes --------------------------------------

    DOMAIN = None
    PROTOCOL = 'http'
    ENCODING = 'utf-8'
    PAGES = {}
    USER_AGENT = 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.4) Gecko/2008111318 Ubuntu/8.10 (intrepid) Firefox/3.0.3'

    # ------ Abstract methods --------------------------------------

    def home(self):
        """
        Go to the home page.
        """
        self.location('%s://%s' % (self.PROTOCOL, self.DOMAIN))

    def login(self):
        """
        Login to the website.

        This function is called when is_logged() returns False and the password
        attribute is not None.
        """
        raise NotImplementedError()

    def is_logged(self):
        """
        Return True if we are logged on website. When Browser tries to access
        to a page, if this method returns False, it calls login().

        It is never called if the password attribute is None.
        """
        raise NotImplementedError()

    # ------ Browser methods ---------------------------------------

    # I'm not a robot, so disable the check of permissions in robots.txt.
    default_features = copy(mechanize.Browser.default_features)
    default_features.remove('_robots')

    def __init__(self, username=None, password=None, firefox_cookies=None,
                 parser=None, history=NoHistory(), proxy=None):
        """
        Constructor of Browser.

        @param username [str] username on website.
        @param password [str] password on website. If it is None, Browser will
                              not try to login.
        @param filefox_cookies [str] Path to cookies' sqlite file.
        @param parser [IParser]  parser to use on HTML files.
        @param hisory [object]  History manager. Default value is an object
                                which does not keep history.
        """
        mechanize.Browser.__init__(self, history=history)
        self.addheaders = [
                ['User-agent', self.USER_AGENT]
            ]

        # Use a proxy
        self.proxy = proxy
        if proxy:
            proto = 'http'
            if proxy.find('://') >= 0:
                proto, domain = proxy.split('://', 1)
            else:
                domain = proxy
            self.set_proxies({proto: domain})

        # Share cookies with firefox
        if firefox_cookies and HAVE_COOKIES:
            self._cookie = FirefoxCookieJar(self.DOMAIN, firefox_cookies)
            self._cookie.load()
            self.set_cookiejar(self._cookie)
        else:
            self._cookie = None

        if parser is None:
            parser = get_parser()()
        elif isinstance(parser, (tuple,list)):
            parser = get_parser(parser)()
        self.parser = parser
        self.page = None
        self.last_update = 0.0
        self.username = username
        self.password = password
        self.lock = RLock()
        if self.password:
            try:
                self.home()
            # Do not abort the build of browser when the website is down.
            except BrowserUnavailable:
                pass

    def __enter__(self):
        self.lock.acquire()

    def __exit__(self, t, v, tb):
        self.lock.release()

    def pageaccess(func):
        def inner(self, *args, **kwargs):
            if not self.page or self.password and not self.page.is_logged():
                self.home()

            return func(self, *args, **kwargs)
        return inner

    @pageaccess
    def keepalive(self):
        self.home()

    def check_location(func):
        def inner(self, *args, **kwargs):
            if args and isinstance(args[0], (str,unicode)) and args[0][0] == '/' and \
               (not self.request or self.request.host != self.DOMAIN):
                args = ('%s://%s%s' % (self.PROTOCOL, self.DOMAIN, args[0]),) + args[1:]

            return func(self, *args, **kwargs)
        return inner

    @check_location
    @retry(BrowserUnavailable, tries=3)
    def openurl(self, *args, **kwargs):
        """
        Open an URL but do not create a Page object.
        """
        debug('Opening URL "%s", %s' % (args, kwargs))
        try:
            return mechanize.Browser.open(self, *args, **kwargs)
        except (mechanize.response_seek_wrapper, urllib2.HTTPError, urllib2.URLError), e:
            raise BrowserUnavailable('%s (url="%s")' % (e, args and args[0] or 'None'))
        except (mechanize.BrowserStateError, BrowserRetry):
            self.home()
            return mechanize.Browser.open(self, *args, **kwargs)

    def submit(self, *args, **kwargs):
        """
        Submit the selected form.
        """
        try:
            self._change_location(mechanize.Browser.submit(self, *args, **kwargs))
        except (mechanize.response_seek_wrapper, urllib2.HTTPError, urllib2.URLError), e:
            self.page = None
            raise BrowserUnavailable(e)
        except (mechanize.BrowserStateError, BrowserRetry), e:
            self.home()
            raise BrowserUnavailable(e)

    def is_on_page(self, pageCls):
        return isinstance(self.page, pageCls)

    def follow_link(self, *args, **kwargs):
        try:
            self._change_location(mechanize.Browser.follow_link(self, *args, **kwargs))
        except (mechanize.response_seek_wrapper, urllib2.HTTPError, urllib2.URLError), e:
            self.page = None
            raise BrowserUnavailable('%s (url="%s")' % (e, args and args[0] or 'None'))
        except (mechanize.BrowserStateError, BrowserRetry), e:
            self.home()
            raise BrowserUnavailable(e)

    @check_location
    @retry(BrowserUnavailable, tries=3)
    def location(self, *args, **kwargs):
        """
        Change location of browser on an URL.

        When the page is loaded, it looks up PAGES to find a regexp which
        matches, and create the object. Then, the 'on_loaded' method of
        this object is called.

        If a password is set, and is_logged() returns False, it tries to login
        with login() and reload the page.
        """
        keep_args = copy(args)
        keep_kwargs = kwargs.copy()

        try:
            self._change_location(mechanize.Browser.open(self, *args, **kwargs))
        except BrowserRetry:
            if not self.page or not args or self.page.url != args[0]:
                self.location(keep_args, keep_kwargs)
        except (mechanize.response_seek_wrapper, urllib2.HTTPError, urllib2.URLError), e:
            self.page = None
            raise BrowserUnavailable('%s (url="%s")' % (e, args and args[0] or 'None'))
        except mechanize.BrowserStateError:
            self.home()
            self.location(*keep_args, **keep_kwargs)

    def _change_location(self, result):
        """
        This function is called when we have moved to a page, to load a Page
        object.
        """

        # Find page from url
        pageCls = None
        page_groups = None
        page_group_dict = None
        for key, value in self.PAGES.items():
            regexp = re.compile('^%s$' % key)
            m = regexp.match(result.geturl())
            if m:
                pageCls = value
                page_groups = m.groups()
                page_group_dict = m.groupdict()
                break

        # Not found
        if not pageCls:
            self.page = None
            #data = result.read()
            #if isinstance(data, unicode):
            #    data = data.encode('utf-8')
            #print data
            warning('Oh my fucking god, there isn\'t any page corresponding to URL %s' % result.geturl())
            return

        debug('[user_id=%s] Went on %s' % (self.username, result.geturl()))
        self.last_update = time.time()

        document = self.parser.parse(result, self.ENCODING)
        self.page = pageCls(self, document, result.geturl(), groups=page_groups, group_dict=page_group_dict)
        self.page.on_loaded()

        if self.password is not None and not self.is_logged():
            debug('!! Relogin !!')
            self.login()
            return

        if self._cookie:
            self._cookie.save()

    def buildurl(self, base, *args, **kwargs):
        """
        Build an URL and escape arguments.
        You can give a serie of tuples in *args (and the order is keept), or
        a dict in **kwargs (but the order is lost).

        Example:
        >>> buildurl('/blah.php', ('a', '&'), ('c', '=')
        '/blah.php?a=%26&b=%3D'
        >>> buildurl('/blah.php', a='&', 'c'='=')
        '/blah.php?b=%3D&a=%26'

        """

        if not args:
            args = kwargs
        if not args:
            return base
        else:
            return '%s?%s' % (base, urllib.urlencode(args))

    def str(self, s):
        if isinstance(s, unicode):
            s = s.encode('iso-8859-15', 'replace')
        return s

    def set_field(self, args, label, field=None, value=None, is_list=False):
        """
        Set a value to a form field.

        @param args [dict]  arguments where to look for value.
        @param label [str]  label in args.
        @param field [str]  field name. If None, use label instead.
        @param value [str]  value to give on field.
        @param is_list [bool]  the field is a list.
        """
        try:
            if not field:
                field = label
            if args.get(label, None) is not None:
                if not value:
                    if is_list:
                        if isinstance(is_list, (list, tuple)):
                            try:
                                value = [self.str(is_list.index(args[label]))]
                            except ValueError, e:
                                if args[label]:
                                    print '[%s] %s: %s' % (label, args[label], e)
                                return
                        else:
                            value = [self.str(args[label])]
                    else:
                        value = self.str(args[label])
                self[field] = value
        except ControlNotFoundError:
            return
