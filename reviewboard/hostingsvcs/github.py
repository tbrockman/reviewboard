import httplib
import urllib2
from django.utils import simplejson
                                            RepositoryError,
                                            TwoFactorAuthCodeRequiredError)
                                 '%(github_public_repo_name)s/issues#issue/%%s',
    supports_bug_trackers = True
    supports_two_factor_auth = True
        except Exception, e:
            if str(e) == 'Not Found':
                  two_factor_auth_code=None, local_site_name=None,
                  *args, **kwargs):
            headers = {}

            if two_factor_auth_code:
                headers['X-GitHub-OTP'] = two_factor_auth_code

                headers=headers,
                body=simplejson.dumps(body))
        except (urllib2.HTTPError, urllib2.URLError), e:
                rsp = simplejson.loads(data)
                response_info = e.info()
                x_github_otp = response_info.get('X-GitHub-OTP', '')

                if x_github_otp.startswith('required;'):
                    raise TwoFactorAuthCodeRequiredError(
                        _('Enter your two-factor authentication code '
                          'and re-enter your password to link your account. '
                          'This code will be sent to you by GitHub.'))

                raise AuthorizationError(str(e))
        except (urllib2.URLError, urllib2.HTTPError):
        except (urllib2.URLError, urllib2.HTTPError):
        elif 'errors' in rsp and status_code == httplib.UNPROCESSABLE_ENTITY:
                                   owner, repo_name)
            return simplejson.loads(data)
        except (urllib2.URLError, urllib2.HTTPError), e:
                rsp = simplejson.loads(data)
                raise Exception(str(e))