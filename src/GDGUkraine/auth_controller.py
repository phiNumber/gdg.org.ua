import cherrypy
import logging

from cherrypy import HTTPError, HTTPRedirect

from blueberrypy.util import to_collection

from oauthlib.oauth2.rfc6749.errors import (MissingCodeError,
                                            MismatchingStateError)

from .api import find_admin_by_email
from .lib.utils.url import url_for_class
from .lib.utils.signals import pub


logger = logging.getLogger(__name__)


class AuthController:
    """AuthController implements authentication via Google's OAuth2"""

    # TODO: decide whether to keep it here or move to test suite
    @cherrypy.expose
    def fake_login(self):
        """This is a method to be used while testing secured area

        It requires `bypass_auth`  option to be enabled in global config
        section and sets fake data about the user into session
        """

        if not cherrypy.config.get('global', {}).get('bypass_auth'):
            raise HTTPError(403)

        req = cherrypy.request
        orm_session = req.orm_session

        cherrypy.session['google_user'] = {
            "given_name": "Petryk",
            "gender": "male",
            "link": "https://plus.google.com/+SvyatoslavSydorenko",
            "picture": "https://www.wired.com/wp-content/uploads/blogs"
                       "/wiredenterprise/wp-content/uploads/2012/06"
                       "/Screen-shot-2012-06-18-at-10.32.45-AM.png",
            "name": "Petryk Piatochkin",
            "hd": "gdg.org.ua",
            "email": "test@gdg.org.ua",
            "id": "133555540822907599802",
            "locale": "uk",
            "verified_email": True,
            "family_name": "Piatochkin"
        }
        cherrypy.session['admin_user'] = to_collection(find_admin_by_email(
            orm_session,
            cherrypy.session['google_user']['email']))

        HTTPRedirect(url_for_class('controller.Root'))

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def google(self, **kwargs):
        req = cherrypy.request
        orm_session = req.orm_session
        try:
            # Aquire API token internally
            pub('oauth-token')

            # Aquire OAuth2Session instance, built with token
            google_api = pub('google-api')

            cherrypy.session['google_user'] = google_api.get(
                'https://www.googleapis.com/oauth2/v1/userinfo').json()

            cherrypy.session['admin_user'] = to_collection(find_admin_by_email(
                orm_session,
                cherrypy.session['google_user']['email']))
            cherrypy.session['google_oauth'] = kwargs

            if cherrypy.session.get('auth_redirect'):
                print('redirect after auth')
                logger.debug('redirect after auth')
                raise HTTPRedirect(cherrypy.session['auth_redirect'])
            else:
                raise HTTPRedirect(url_for_class('controller.Root'))

            return cherrypy.session['admin_user']
        except MissingCodeError as mce:
            raise HTTPError(401,
                            'Error: {}'.format(kwargs.get('error'))) from mce
        except (MismatchingStateError, KeyError) as wrong_state:
            raise HTTPRedirect(
                url_for_class('controller.Root.auth')) from wrong_state

    # index = google

    @cherrypy.expose
    def index(self, return_url=None):
        return_url = (return_url
                      if return_url
                      else cherrypy.request.headers.get('Referer'))

        if return_url is not None and \
           return_url.stratswith(['/', 'https://', 'http://']) \
           and not return_url.startswith('/auth'):
            cherrypy.session['auth_redirect'] = return_url

        authorization_url = pub('oauth-url')

        raise HTTPRedirect(authorization_url)

    @cherrypy.expose
    def logout(self, return_url=None):
        for key in ['google_oauth', 'google_user',
                    'admin_user', 'auth_redirect']:
            if cherrypy.session.get(key):
                del cherrypy.session[key]

        return_url = (return_url
                      if return_url
                      else cherrypy.request.headers.get('Referer', '/'))

        if (any(return_url.startswith(_)
                for _ in ['/', 'https://', 'http://']) and
                not return_url.startswith('/auth')):
            raise HTTPRedirect(return_url)

        raise HTTPRedirect(url_for_class('controller.Root'))
