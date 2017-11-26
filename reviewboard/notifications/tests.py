from __future__ import unicode_literals

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.http import Http404
from django.template import TemplateSyntaxError
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.utils import six
from django.utils.datastructures import MultiValueDict
from django.utils.six.moves import range
from django.utils.six.moves.urllib.request import OpenerDirector
from djblets.mail.testing import DmarcDnsTestsMixin
from djblets.mail.utils import (build_email_address,
                                build_email_address_for_user)
from djblets.siteconfig.models import SiteConfiguration
from djblets.testing.decorators import add_fixtures
from kgb import SpyAgency

from reviewboard.accounts.models import Profile, ReviewRequestVisit
from reviewboard.admin.siteconfig import load_site_config
from reviewboard.diffviewer.models import FileDiff
from reviewboard.notifications.email.message import \
    EmailMessage, prepare_base_review_request_mail
from reviewboard.notifications.email.utils import (
    build_recipients,
    get_email_addresses_for_group,
    recipients_to_addresses,
    send_email)
from reviewboard.notifications.email.views import BasePreviewEmailView
from reviewboard.notifications.models import WebHookTarget
from reviewboard.notifications.webhooks import (FakeHTTPRequest,
                                                dispatch_webhook_event,
                                                render_custom_content)
from reviewboard.reviews.models import (Group,
                                        Review,
                                        ReviewRequest,
                                        ReviewRequestDraft)
from reviewboard.scmtools.core import PRE_CREATION
from reviewboard.site.models import LocalSite
from reviewboard.testing import TestCase
from reviewboard.webapi.models import WebAPIToken


_CONSOLE_EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


class EmailTestHelper(object):
    def setUp(self):
        super(EmailTestHelper, self).setUp()

        mail.outbox = []
        self.sender = 'noreply@example.com'

        self._old_enable_smart_spoofing = settings.EMAIL_ENABLE_SMART_SPOOFING
        settings.EMAIL_ENABLE_SMART_SPOOFING = True

    def tearDown(self):
        super(EmailTestHelper, self).tearDown()

        settings.EMAIL_ENABLE_SMART_SPOOFING = self._old_enable_smart_spoofing

    def assertValidRecipients(self, user_list, group_list=[]):
        recipient_list = mail.outbox[0].to + mail.outbox[0].cc
        self.assertEqual(len(recipient_list), len(user_list) + len(group_list))

        for user in user_list:
            self.assertTrue(build_email_address_for_user(
                User.objects.get(username=user)) in recipient_list,
                "user %s was not found in the recipient list" % user)

        groups = Group.objects.filter(name__in=group_list, local_site=None)
        for group in groups:
            for address in get_email_addresses_for_group(group):
                self.assertTrue(
                    address in recipient_list,
                    "group %s was not found in the recipient list" % address)


class UserEmailTests(EmailTestHelper, TestCase):
    def setUp(self):
        super(UserEmailTests, self).setUp()

        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set("mail_send_new_user_mail", True)
        siteconfig.save()
        load_site_config()

    def test_new_user_email(self):
        """
        Testing sending an e-mail after a new user has successfully registered.
        """
        new_user_info = {
            'username': 'NewUser',
            'password1': 'password',
            'password2': 'password',
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'User'
        }

        # Registration request have to be sent twice since djblets need to
        # validate cookies on the second request.
        self.client.get('/account/register/')
        self.client.post('/account/register/', new_user_info)

        siteconfig = SiteConfiguration.objects.get_current()
        admin_name = siteconfig.get('site_admin_name')
        admin_email_addr = siteconfig.get('site_admin_email')

        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox[0]
        self.assertEqual(email.subject,
                         "New Review Board user registration for NewUser")

        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'], settings.SERVER_EMAIL)
        self.assertEqual(email.to[0],
                         build_email_address(full_name=admin_name,
                                             email=admin_email_addr))


class ReviewRequestEmailTests(EmailTestHelper, DmarcDnsTestsMixin, SpyAgency,
                              TestCase):
    """Tests the e-mail support."""

    fixtures = ['test_users']

    def setUp(self):
        super(ReviewRequestEmailTests, self).setUp()

        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set("mail_send_review_mail", True)
        siteconfig.set("mail_default_from", self.sender)
        siteconfig.save()
        load_site_config()

    def test_new_review_request_email(self):
        """Testing sending an e-mail when creating a new review request"""
        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_people.add(User.objects.get(username='grumpy'))
        review_request.target_people.add(User.objects.get(username='doc'))
        review_request.publish(review_request.submitter)

        from_email = build_email_address_for_user(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertEqual(mail.outbox[0].subject,
                         'Review Request %s: My test review request'
                         % review_request.pk)
        self.assertValidRecipients(['grumpy', 'doc'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_new_review_request_email_with_dmarc_deny(self):
        """Testing sending an e-mail when creating a new review request with
        From spoofing blocked by DMARC
        """
        self.dmarc_txt_records['_dmarc.example.com'] = 'v=DMARC1; p=reject;'

        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_people.add(User.objects.get(username='grumpy'))
        review_request.target_people.add(User.objects.get(username='doc'))
        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'],
                         'Doc Dwarf via Review Board <noreply@example.com>')
        self.assertEqual(mail.outbox[0].subject,
                         'Review Request %s: My test review request'
                         % review_request.pk)
        self.assertValidRecipients(['grumpy', 'doc'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_review_request_email_local_site_group(self):
        """Testing sending email when a group member is part of a Local Site"""
        # This was bug 3581.
        local_site = LocalSite.objects.create(name=self.local_site_name)

        group = self.create_review_group()
        user = User.objects.get(username='grumpy')

        local_site.users.add(user)
        local_site.admins.add(user)
        local_site.save()
        group.users.add(user)
        group.save()

        review_request = self.create_review_request()
        review_request.target_groups.add(group)
        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertValidRecipients(['doc', 'grumpy'])

    def test_review_email(self):
        """Testing sending an e-mail when replying to a review request"""
        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_people.add(User.objects.get(username='grumpy'))
        review_request.target_people.add(User.objects.get(username='doc'))
        review_request.publish(review_request.submitter)

        # Clear the outbox.
        mail.outbox = []

        review = self.create_review(review_request=review_request)
        review.publish()

        from_email = build_email_address_for_user(review.user)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'], from_email)
        self.assertEqual(email._headers['X-ReviewBoard-URL'],
                         'http://example.com/')
        self.assertEqual(email._headers['X-ReviewRequest-URL'],
                         'http://example.com/r/%s/'
                         % review_request.display_id)
        self.assertEqual(email.subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.display_id)
        self.assertValidRecipients([
            review_request.submitter.username,
            'grumpy',
            'doc',
        ])

        message = email.message()
        self.assertEqual(message['Sender'], self._get_sender(review.user))

    def test_review_email_with_dmarc_deny(self):
        """Testing sending an e-mail when replying to a review request with
        From spoofing blocked by DMARC
        """
        self.dmarc_txt_records['_dmarc.example.com'] = 'v=DMARC1; p=reject;'

        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_people.add(User.objects.get(username='grumpy'))
        review_request.target_people.add(User.objects.get(username='doc'))
        review_request.publish(review_request.submitter)

        # Clear the outbox.
        mail.outbox = []

        review = self.create_review(review_request=review_request)
        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'],
                         'Dopey Dwarf via Review Board <noreply@example.com>')
        self.assertEqual(email._headers['X-ReviewBoard-URL'],
                         'http://example.com/')
        self.assertEqual(email._headers['X-ReviewRequest-URL'],
                         'http://example.com/r/%s/'
                         % review_request.display_id)
        self.assertEqual(email.subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.display_id)
        self.assertValidRecipients([
            review_request.submitter.username,
            'grumpy',
            'doc',
        ])

        message = email.message()
        self.assertEqual(message['Sender'], self._get_sender(review.user))

    @add_fixtures(['test_site'])
    def test_review_email_with_site(self):
        """Testing sending an e-mail when replying to a review request
        on a Local Site
        """
        review_request = self.create_review_request(
            summary='My test review request',
            with_local_site=True)
        review_request.target_people.add(User.objects.get(username='grumpy'))
        review_request.target_people.add(User.objects.get(username='doc'))
        review_request.publish(review_request.submitter)

        # Ensure all the reviewers are on the site.
        site = review_request.local_site
        site.users.add(*list(review_request.target_people.all()))

        # Clear the outbox.
        mail.outbox = []

        review = self.create_review(review_request=review_request)
        review.publish()

        from_email = build_email_address_for_user(review.user)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'], from_email)
        self.assertEqual(email._headers['X-ReviewBoard-URL'],
                         'http://example.com/s/local-site-1/')
        self.assertEqual(email._headers['X-ReviewRequest-URL'],
                         'http://example.com/s/local-site-1/r/%s/'
                         % review_request.display_id)
        self.assertEqual(email.subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.display_id)
        self.assertValidRecipients([
            review_request.submitter.username,
            'grumpy',
            'doc',
        ])

        message = email.message()
        self.assertEqual(message['Sender'], self._get_sender(review.user))

    def test_profile_should_send_email_setting(self):
        """Testing the Profile.should_send_email setting"""
        grumpy = User.objects.get(username='grumpy')
        profile = grumpy.get_profile()
        profile.should_send_email = False
        profile.save()

        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_people.add(grumpy)
        review_request.target_people.add(User.objects.get(username='doc'))
        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertValidRecipients(['doc'])

    def test_review_request_closed_no_email(self):
        """Tests e-mail is not generated when a review request is closed and
        e-mail setting is False
        """
        review_request = self.create_review_request()
        review_request.publish(review_request.submitter)

        # Clear the outbox.
        mail.outbox = []

        review_request.close(ReviewRequest.SUBMITTED, review_request.submitter)

        # Verify that no email is generated as option is false by default
        self.assertEqual(len(mail.outbox), 0)

    def test_review_request_closed_with_email(self):
        """Tests e-mail is generated when a review request is closed and
        e-mail setting is True
        """
        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set('mail_send_review_close_mail', True)
        siteconfig.save()
        load_site_config()

        try:
            review_request = self.create_review_request()
            review_request.publish(review_request.submitter)

            # Clear the outbox.
            mail.outbox = []

            review_request.close(ReviewRequest.SUBMITTED,
                                 review_request.submitter)

            from_email = build_email_address_for_user(review_request.submitter)

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].from_email, self.sender)
            self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)

            message = mail.outbox[0].message()
            self.assertTrue('This change has been marked as submitted'
                            in message.as_string())
        finally:
            # Reset settings for review close requests
            siteconfig.set('mail_send_review_close_mail', False)
            siteconfig.save()
            load_site_config()

    def test_review_request_close_with_email_and_dmarc_deny(self):
        """Tests e-mail is generated when a review request is closed and
        e-mail setting is True and From spoofing blocked by DMARC
        """
        self.dmarc_txt_records['_dmarc.example.com'] = 'v=DMARC1; p=reject;'

        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set('mail_send_review_close_mail', True)
        siteconfig.save()
        load_site_config()

        try:
            review_request = self.create_review_request()
            review_request.publish(review_request.submitter)

            # Clear the outbox.
            mail.outbox = []

            review_request.close(ReviewRequest.SUBMITTED,
                                 review_request.submitter)

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].from_email, self.sender)
            self.assertEqual(mail.outbox[0].extra_headers['From'],
                             'Doc Dwarf via Review Board '
                             '<noreply@example.com>')

            message = mail.outbox[0].message()
            self.assertTrue('This change has been marked as submitted'
                            in message.as_string())
        finally:
            # Reset settings for review close requests
            siteconfig.set('mail_send_review_close_mail', False)
            siteconfig.save()
            load_site_config()

    def test_review_to_owner_only(self):
        """Test that e-mails from reviews published to the submitter only will
        only go to the submitter and the reviewer
        """
        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set('mail_send_review_mail', True)
        siteconfig.save()

        review_request = self.create_review_request(public=True, publish=False)
        review_request.target_people = [User.objects.get(username='grumpy')]
        review_request.save()

        review = self.create_review(review_request=review_request,
                                    publish=False)

        review.publish(to_owner_only=True)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]

        self.assertEqual(message.cc, [])
        self.assertEqual(len(message.to), 2)

        self.assertEqual(
            set(message.to),
            set([build_email_address_for_user(review.user),
                 build_email_address_for_user(review_request.submitter)]))

    def test_review_reply_email(self):
        """Testing sending an e-mail when replying to a review"""
        review_request = self.create_review_request(
            summary='My test review request')
        review_request.publish(review_request.submitter)

        base_review = self.create_review(review_request=review_request)
        base_review.publish()

        # Clear the outbox.
        mail.outbox = []

        reply = self.create_reply(base_review)
        reply.publish()

        from_email = build_email_address_for_user(reply.user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.pk)
        self.assertValidRecipients([
            review_request.submitter.username,
            base_review.user.username,
            reply.user.username,
        ])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'], self._get_sender(reply.user))

    def test_review_reply_email_with_dmarc_deny(self):
        """Testing sending an e-mail when replying to a review with From
        spoofing blocked by DMARC
        """
        self.dmarc_txt_records['_dmarc.example.com'] = 'v=DMARC1; p=reject;'

        review_request = self.create_review_request(
            summary='My test review request')
        review_request.publish(review_request.submitter)

        base_review = self.create_review(review_request=review_request)
        base_review.publish()

        # Clear the outbox.
        mail.outbox = []

        reply = self.create_reply(base_review)
        reply.publish()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'],
                         'Grumpy Dwarf via Review Board <noreply@example.com>')
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.pk)
        self.assertValidRecipients([
            review_request.submitter.username,
            base_review.user.username,
            reply.user.username,
        ])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'], self._get_sender(reply.user))

    def test_update_review_request_email(self):
        """Testing sending an e-mail when updating a review request"""
        group = Group.objects.create(name='devgroup',
                                     mailing_list='devgroup@example.com')

        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_groups.add(group)
        review_request.email_message_id = "junk"
        review_request.publish(review_request.submitter)

        from_email = build_email_address_for_user(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.pk)
        self.assertValidRecipients([review_request.submitter.username],
                                   ['devgroup'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_update_review_request_email_with_dmarc_deny(self):
        """Testing sending an e-mail when updating a review request with
        From spoofing blocked by DMARC
        """
        self.dmarc_txt_records['_dmarc.example.com'] = 'v=DMARC1; p=reject;'

        group = Group.objects.create(name='devgroup',
                                     mailing_list='devgroup@example.com')

        review_request = self.create_review_request(
            summary='My test review request')
        review_request.target_groups.add(group)
        review_request.email_message_id = "junk"
        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'],
                         'Doc Dwarf via Review Board <noreply@example.com>')
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.pk)
        self.assertValidRecipients([review_request.submitter.username],
                                   ['devgroup'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_add_reviewer_review_request_email(self):
        """Testing limited e-mail recipients
        when adding a reviewer to an existing review request
        """
        review_request = self.create_review_request(
            summary='My test review request',
            public=True)
        review_request.email_message_id = "junk"
        review_request.target_people.add(User.objects.get(username='dopey'))
        review_request.save()

        draft = ReviewRequestDraft.create(review_request)
        draft.target_people.add(User.objects.get(username='grumpy'))
        draft.publish(user=review_request.submitter)

        from_email = build_email_address_for_user(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.pk)
        # The only included users should be the submitter and 'grumpy' (not
        # 'dopey', since he was already included on the review request earlier)
        self.assertValidRecipients([review_request.submitter.username,
                                    'grumpy'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_add_group_review_request_email(self):
        """Testing limited e-mail recipients
        when adding a group to an existing review request
        """
        existing_group = Group.objects.create(
            name='existing', mailing_list='existing@example.com')
        review_request = self.create_review_request(
            summary='My test review request',
            public=True)
        review_request.email_message_id = "junk"
        review_request.target_groups.add(existing_group)
        review_request.target_people.add(User.objects.get(username='dopey'))
        review_request.save()

        new_group = Group.objects.create(name='devgroup',
                                         mailing_list='devgroup@example.com')
        draft = ReviewRequestDraft.create(review_request)
        draft.target_groups.add(new_group)
        draft.publish(user=review_request.submitter)

        from_email = build_email_address_for_user(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: My test review request'
                         % review_request.pk)
        # The only included users should be the submitter and 'devgroup' (not
        # 'dopey' or 'existing', since they were already included on the
        # review request earlier)
        self.assertValidRecipients([review_request.submitter.username],
                                   ['devgroup'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_limited_recipients_other_fields(self):
        """Testing that recipient limiting only happens when adding reviewers
        """
        review_request = self.create_review_request(
            summary='My test review request',
            public=True)
        review_request.email_message_id = "junk"
        review_request.target_people.add(User.objects.get(username='dopey'))
        review_request.save()

        draft = ReviewRequestDraft.create(review_request)
        draft.summary = 'Changed summary'
        draft.target_people.add(User.objects.get(username='grumpy'))
        draft.publish(user=review_request.submitter)

        from_email = build_email_address_for_user(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertEqual(mail.outbox[0].subject,
                         'Re: Review Request %s: Changed summary'
                         % review_request.pk)
        self.assertValidRecipients([review_request.submitter.username,
                                    'dopey', 'grumpy'])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_limited_recipients_no_email(self):
        """Testing limited e-mail recipients when operation results in zero
        recipients
        """
        review_request = self.create_review_request(
            summary='My test review request',
            public=True)
        review_request.email_message_id = "junk"
        review_request.target_people.add(User.objects.get(username='dopey'))
        review_request.save()

        profile, is_new = Profile.objects.get_or_create(
            user=review_request.submitter)
        profile.should_send_own_updates = False
        profile.save()

        draft = ReviewRequestDraft.create(review_request)
        draft.target_people.remove(User.objects.get(username='dopey'))
        draft.publish(user=review_request.submitter)

        self.assertEqual(len(mail.outbox), 0)

    def test_recipients_with_muted_review_requests(self):
        """Testing e-mail recipients when users mute a review request"""
        dopey = User.objects.get(username='dopey')
        admin = User.objects.get(username='admin')

        group = Group.objects.create(name='group')
        group.users.add(admin)
        group.save()

        review_request = self.create_review_request(
            summary='My test review request',
            public=True)
        review_request.target_people.add(dopey)
        review_request.target_people.add(User.objects.get(username='grumpy'))
        review_request.target_groups.add(group)
        review_request.save()

        visit = self.create_visit(review_request, ReviewRequestVisit.MUTED,
                                  dopey)
        visit.save()

        visit = self.create_visit(review_request, ReviewRequestVisit.MUTED,
                                  admin)
        visit.save()

        draft = ReviewRequestDraft.create(review_request)
        draft.summary = 'Summary changed'
        draft.publish(user=review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertValidRecipients(['doc', 'grumpy'])

    def test_group_member_not_receive_email(self):
        """Testing sending review e-mails and filtering out the review
        submitter when they are part of a review group assigned to the request
        """
        # See issue 3985.
        submitter = User.objects.get(username='doc')
        profile = Profile.objects.get_or_create(user=submitter)[0]
        profile.should_send_own_updates = False
        profile.save()

        reviewer = User.objects.get(username='dopey')

        group = self.create_review_group()
        group.users.add(submitter)

        review_request = self.create_review_request(public=True)
        review_request.target_groups.add(group)
        review_request.target_people.add(reviewer)
        review_request.save()

        review = self.create_review(review_request, user=submitter)
        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]

        self.assertListEqual(
            msg.to,
            [build_email_address_for_user(reviewer)])

        self.assertListEqual(msg.cc, [])

    def test_local_site_user_filters(self):
        """Testing sending e-mails and filtering out users not on a local site
        """
        test_site = LocalSite.objects.create(name=self.local_site_name)

        site_user1 = User.objects.create(
            username='site_user1',
            email='site_user1@example.com')
        site_user2 = User.objects.create(
            username='site_user2',
            email='site_user2@example.com')
        site_user3 = User.objects.create(
            username='site_user3',
            email='site_user3@example.com')
        site_user4 = User.objects.create(
            username='site_user4',
            email='site_user4@example.com')
        site_user5 = User.objects.create(
            username='site_user5',
            email='site_user5@example.com')
        non_site_user1 = User.objects.create(
            username='non_site_user1',
            email='non_site_user1@example.com')
        non_site_user2 = User.objects.create(
            username='non_site_user2',
            email='non_site_user2@example.com')
        non_site_user3 = User.objects.create(
            username='non_site_user3',
            email='non_site_user3@example.com')

        test_site.admins.add(site_user1)
        test_site.users.add(site_user2)
        test_site.users.add(site_user3)
        test_site.users.add(site_user4)
        test_site.users.add(site_user5)

        group = Group.objects.create(name='my-group',
                                     display_name='My Group',
                                     local_site=test_site)
        group.users.add(site_user5)
        group.users.add(non_site_user3)

        review_request = self.create_review_request(with_local_site=True,
                                                    local_id=123)
        review_request.email_message_id = "junk"
        review_request.target_people = [site_user1, site_user2, site_user3,
                                        non_site_user1]
        review_request.target_groups = [group]

        review = Review.objects.create(review_request=review_request,
                                       user=site_user4)
        review.publish()

        review = Review.objects.create(review_request=review_request,
                                       user=non_site_user2)
        review.publish()

        from_email = build_email_address_for_user(review_request.submitter)

        # Now that we're set up, send another e-mail.
        mail.outbox = []
        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, self.sender)
        self.assertEqual(mail.outbox[0].extra_headers['From'], from_email)
        self.assertValidRecipients(
            ['site_user1', 'site_user2', 'site_user3', 'site_user4',
             'site_user5', review_request.submitter.username], [])

        message = mail.outbox[0].message()
        self.assertEqual(message['Sender'],
                         self._get_sender(review_request.submitter))

    def test_review_request_email_with_unicode_summary(self):
        """Testing sending a review request e-mail with a unicode subject"""
        self.spy_on(logging.exception)

        with self.settings(EMAIL_BACKEND=_CONSOLE_EMAIL_BACKEND):
            review_request = self.create_review_request()
            review_request.summary = '\ud83d\ude04'

            review_request.target_people.add(User.objects.get(
                username='grumpy'))
            review_request.target_people.add(User.objects.get(username='doc'))
            review_request.publish(review_request.submitter)

        self.assertIsNotNone(review_request.email_message_id)
        self.assertFalse(logging.exception.spy.called)

    def test_review_request_email_with_unicode_description(self):
        """Testing sending a review request e-mail with a unicode
        description
        """
        self.spy_on(logging.exception)

        with self.settings(EMAIL_BACKEND=_CONSOLE_EMAIL_BACKEND):
            review_request = self.create_review_request()
            review_request.description = '\ud83d\ude04'

            review_request.target_people.add(
                User.objects.get(username='grumpy'))
            review_request.target_people.add(
                User.objects.get(username='doc'))
            review_request.publish(review_request.submitter)

        self.assertIsNotNone(review_request.email_message_id)
        self.assertFalse(logging.exception.spy.called)

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_added_file(self):
        """Testing sending a review request e-mail with added files in the
        diffset
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        filediff = self.create_filediff(diffset=diffset,
                                        source_file='/dev/null',
                                        source_revision=PRE_CREATION)

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertTrue('X-ReviewBoard-Diff-For' in message._headers)
        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')

        self.assertEqual(len(diff_headers), 1)
        self.assertFalse(filediff.source_file in diff_headers)
        self.assertTrue(filediff.dest_file in diff_headers)

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_added_files_over_header_limit(self):
        """Testing sending a review request e-mail with added files in the
        diffset such that the filename headers take up more than 8192
        characters
        """
        self.spy_on(logging.warning)
        self.maxDiff = None

        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        prefix = 'X' * 97

        filediffs = []

        # Each filename is 100 characters long. For each header we add 26
        # characters: the key, a ': ', and the terminating '\r\n'.
        # 8192 / (100 + 26) rounds down to 65. We'll bump it up to 70 just
        # to be careful.
        for i in range(70):
            filename = '%s%#03d' % (prefix, i)
            self.assertEqual(len(filename), 100)
            filediffs.append(self.create_filediff(
                diffset=diffset,
                source_file=filename,
                dest_file=filename,
                source_revision=PRE_CREATION,
                diff='',
                save=False))

        FileDiff.objects.bulk_create(filediffs)

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-Diff-For', message._headers)
        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')

        self.assertEqual(len(logging.warning.spy.calls), 1)
        self.assertEqual(len(diff_headers), 65)

        self.assertEqual(
            logging.warning.spy.calls[0].args,
            ('Unable to store all filenames in the X-ReviewBoard-Diff-For '
             'headers when sending e-mail for review request %s: The header '
             'size exceeds the limit of %s. Remaining headers have been '
             'omitted.',
             1,
             8192))

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_deleted_file(self):
        """Testing sending a review request e-mail with deleted files in the
        diffset
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        filediff = self.create_filediff(diffset=diffset,
                                        dest_file='/dev/null',
                                        status=FileDiff.DELETED)

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertTrue('X-ReviewBoard-Diff-For' in message._headers)
        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')

        self.assertEqual(len(diff_headers), 1)
        self.assertTrue(filediff.source_file in diff_headers)
        self.assertFalse(filediff.dest_file in diff_headers)

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_moved_file(self):
        """Testing sending a review request e-mail with moved files in the
        diffset
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        filediff = self.create_filediff(diffset=diffset,
                                        source_file='foo',
                                        dest_file='bar',
                                        status=FileDiff.MOVED)

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertTrue('X-ReviewBoard-Diff-For' in message._headers)
        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')

        self.assertEqual(len(diff_headers), 2)
        self.assertTrue(filediff.source_file in diff_headers)
        self.assertTrue(filediff.dest_file in diff_headers)

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_copied_file(self):
        """Testing sending a review request e-mail with copied files in the
        diffset
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        filediff = self.create_filediff(diffset=diffset,
                                        source_file='foo',
                                        dest_file='bar',
                                        status=FileDiff.COPIED)

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertTrue('X-ReviewBoard-Diff-For' in message._headers)
        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')

        self.assertEqual(len(diff_headers), 2)
        self.assertTrue(filediff.source_file in diff_headers)
        self.assertTrue(filediff.dest_file in diff_headers)

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_modified_file(self):
        """Testing sending a review request e-mail with modified files in
        the diffset
        """
        # Bug #4572 reported that the 'X-ReviewBoard-Diff-For' header appeared
        # only for newly created files and moved files. This test is to check
        # that the header appears for modified files as well.
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        filediff = self.create_filediff(diffset=diffset,
                                        source_file='foo',
                                        dest_file='bar',
                                        status=FileDiff.MODIFIED)

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-Diff-For', message._headers)

        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')
        self.assertEqual(len(diff_headers), 2)
        self.assertIn(filediff.source_file, diff_headers)
        self.assertIn(filediff.dest_file, diff_headers)

    @add_fixtures(['test_scmtools'])
    def test_review_request_email_with_multiple_files(self):
        """Testing sending a review request e-mail with multiple files in the
        diffset
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository)
        diffset = self.create_diffset(review_request=review_request)
        filediffs = [
            self.create_filediff(diffset=diffset,
                                 source_file='foo',
                                 dest_file='bar',
                                 status=FileDiff.MOVED),
            self.create_filediff(diffset=diffset,
                                 source_file='baz',
                                 dest_file='/dev/null',
                                 status=FileDiff.DELETED)
        ]

        review_request.publish(review_request.submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertTrue('X-ReviewBoard-Diff-For' in message._headers)
        diff_headers = message._headers.getlist('X-ReviewBoard-Diff-For')

        self.assertEqual(
            set(diff_headers),
            {
                filediffs[0].source_file,
                filediffs[0].dest_file,
                filediffs[1].source_file,
            })

    def test_extra_headers_dict(self):
        """Testing sending extra headers as a dict with an e-mail message"""
        review_request = self.create_review_request()
        submitter = review_request.submitter
        send_email(prepare_base_review_request_mail,
                   user=submitter,
                   review_request=review_request,
                   subject='Foo',
                   in_reply_to=None,
                   to_field=[submitter],
                   cc_field=[],
                   template_name_base='notifications/review_request_email',
                   extra_headers={'X-Foo': 'Bar'})

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-Foo', message._headers)
        self.assertEqual(message._headers['X-Foo'], 'Bar')

    def test_extra_headers_multivalue_dict(self):
        """Testing sending extra headers as a MultiValueDict with an e-mail
        message
        """
        header_values = ['Bar', 'Baz']
        review_request = self.create_review_request()
        submitter = review_request.submitter
        send_email(prepare_base_review_request_mail,
                   user=review_request.submitter,
                   review_request=review_request,
                   subject='Foo',
                   in_reply_to=None,
                   to_field=[submitter],
                   cc_field=[],
                   template_name_base='notifications/review_request_email',
                   extra_headers=MultiValueDict({'X-Foo': header_values}))

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-Foo', message._headers)
        self.assertEqual(set(message._headers.getlist('X-Foo')),
                         set(header_values))

    def test_review_no_shipit_headers(self):
        """Testing sending a review e-mail without a 'Ship It!'"""
        review_request = self.create_review_request(public=True)

        self.create_review(review_request,
                           body_top=Review.SHIP_IT_TEXT,
                           body_bottom='',
                           publish=True)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertNotIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_only_headers(self):
        """Testing sending a review e-mail with only a 'Ship It!'"""
        review_request = self.create_review_request(public=True)

        self.create_review(review_request,
                           body_top=Review.SHIP_IT_TEXT,
                           body_bottom='',
                           ship_it=True,
                           publish=True)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_only_headers_no_text(self):
        """Testing sending a review e-mail with only a 'Ship It!' and no text
        """
        review_request = self.create_review_request(public=True)

        self.create_review(review_request,
                           body_top='',
                           body_bottom='',
                           ship_it=True,
                           publish=True)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_headers_custom_top_text(self):
        """Testing sending a review e-mail with a 'Ship It' and custom top text
        """
        review_request = self.create_review_request(public=True)

        self.create_review(review_request,
                           body_top='Some general information.',
                           body_bottom='',
                           ship_it=True,
                           publish=True)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_headers_bottom_text(self):
        """Testing sending a review e-mail with a 'Ship It' and bottom text"""
        review_request = self.create_review_request(public=True)

        self.create_review(review_request,
                           body_top=Review.SHIP_IT_TEXT,
                           body_bottom='Some comments',
                           ship_it=True,
                           publish=True)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    @add_fixtures(['test_scmtools'])
    def test_review_shipit_headers_comments(self):
        """Testing sending a review e-mail with a 'Ship It' and diff comments
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository,
                                                    public=True)

        diffset = self.create_diffset(review_request)
        filediff = self.create_filediff(diffset)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_diff_comment(review, filediff)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    @add_fixtures(['test_scmtools'])
    def test_review_shipit_headers_comments_opened_issue(self):
        """Testing sending a review e-mail with a 'Ship It' and diff comments
        with opened issue
        """
        repository = self.create_repository(tool_name='Test')
        review_request = self.create_review_request(repository=repository,
                                                    public=True)

        diffset = self.create_diffset(review_request)
        filediff = self.create_filediff(diffset)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_diff_comment(review, filediff, issue_opened=True)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertTrue(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                        message.message().as_string())

    def test_review_shipit_headers_attachment_comments(self):
        """Testing sending a review e-mail with a 'Ship It' and file attachment
        comments
        """
        review_request = self.create_review_request(public=True)

        file_attachment = self.create_file_attachment(review_request)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_file_attachment_comment(review, file_attachment)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_headers_attachment_comments_opened_issue(self):
        """Testing sending a review e-mail with a 'Ship It' and file attachment
        comments with opened issue
        """
        review_request = self.create_review_request(public=True)

        file_attachment = self.create_file_attachment(review_request)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_file_attachment_comment(review, file_attachment,
                                            issue_opened=True)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertTrue(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                        message.message().as_string())

    def test_review_shipit_headers_screenshot_comments(self):
        """Testing sending a review e-mail with a 'Ship It' and screenshot
        comments
        """
        review_request = self.create_review_request(public=True)

        screenshot = self.create_screenshot(review_request)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_screenshot_comment(review, screenshot)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_headers_screenshot_comments_opened_issue(self):
        """Testing sending a review e-mail with a 'Ship It' and screenshot
        comments with opened issue
        """
        review_request = self.create_review_request(public=True)

        screenshot = self.create_screenshot(review_request)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_screenshot_comment(review, screenshot, issue_opened=True)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertTrue(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                        message.message().as_string())

    def test_review_shipit_headers_general_comments(self):
        """Testing sending a review e-mail with a 'Ship It' and general
        comments
        """
        review_request = self.create_review_request(public=True)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_general_comment(review)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertFalse(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                         message.message().as_string())

    def test_review_shipit_headers_general_comments_opened_issue(self):
        """Testing sending a review e-mail with a 'Ship It' and general
        comments with opened issue
        """
        review_request = self.create_review_request(public=True)

        review = self.create_review(review_request,
                                    body_top=Review.SHIP_IT_TEXT,
                                    body_bottom='',
                                    ship_it=True,
                                    publish=False)

        self.create_general_comment(review, issue_opened=True)

        review.publish()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertIn('X-ReviewBoard-ShipIt', message._headers)
        self.assertNotIn('X-ReviewBoard-ShipIt-Only', message._headers)
        self.assertTrue(Review.FIX_IT_THEN_SHIP_IT_TEXT in
                        message.message().as_string())

    def test_change_ownership_email(self):
        """Testing sending a review request e-mail when the owner is being
        changed
        """
        admin_user = User.objects.get(username='admin')
        admin_email = build_email_address_for_user(admin_user)
        review_request = self.create_review_request(public=True)
        submitter = review_request.submitter
        submitter_email = build_email_address_for_user(submitter)

        draft = ReviewRequestDraft.create(review_request)
        draft.owner = admin_user
        draft.save()
        review_request.publish(submitter)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertEqual(message.extra_headers['From'], submitter_email)
        self.assertSetEqual(set(message.to),
                            {admin_email, submitter_email})

    def test_change_ownership_email_not_submitter(self):
        """Testing sending a review request e-mail when the owner is being
        changed by someone else
        """
        admin_user = User.objects.get(username='admin')
        admin_email = build_email_address_for_user(admin_user)
        review_request = self.create_review_request(public=True)
        submitter = review_request.submitter
        submitter_email = build_email_address_for_user(submitter)

        draft = ReviewRequestDraft.create(review_request)
        draft.owner = admin_user
        draft.save()
        review_request.publish(admin_user)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]

        self.assertEqual(message.extra_headers['From'], admin_email)
        self.assertSetEqual(set(message.to),
                            {admin_email, submitter_email})

    def _get_sender(self, user):
        return build_email_address(full_name=user.get_full_name(),
                                   email=self.sender)


class WebAPITokenEmailTests(EmailTestHelper, TestCase):
    """Unit tests for WebAPIToken creation e-mails."""

    def setUp(self):
        super(WebAPITokenEmailTests, self).setUp()

        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set('mail_send_new_user_mail', False)
        siteconfig.save()
        load_site_config()

        self.user = User.objects.create(username='test-user',
                                        first_name='Sample',
                                        last_name='User',
                                        email='test-user@example.com')
        self.assertEqual(len(mail.outbox), 0)

    def test_create_token(self):
        """Testing sending e-mail when a new API Token is created"""
        webapi_token = WebAPIToken.objects.generate_token(user=self.user,
                                                          note='Test',
                                                          policy={})

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        html_body = email.alternatives[0][0]
        partial_token = '%s...' % webapi_token.token[:10]

        self.assertEqual(email.subject, 'New Review Board API token created')
        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'], settings.SERVER_EMAIL)
        self.assertEqual(email.to[0], build_email_address_for_user(self.user))
        self.assertNotIn(webapi_token.token, email.body)
        self.assertNotIn(webapi_token.token, html_body)
        self.assertIn(partial_token, email.body)
        self.assertIn(partial_token, html_body)
        self.assertIn('A new API token has been added', email.body)
        self.assertIn('A new API token has been added', html_body)

    def test_create_token_no_email(self):
        """Testing WebAPIToken.objects.generate_token does not send e-mail
        when auto_generated is True
        """
        WebAPIToken.objects.generate_token(user=self.user,
                                           note='Test',
                                           policy={},
                                           auto_generated=True)

        self.assertEqual(len(mail.outbox), 0)

    def test_update_token(self):
        """Testing sending e-mail when an existing API Token is updated"""
        webapi_token = WebAPIToken.objects.generate_token(user=self.user,
                                                          note='Test',
                                                          policy={})
        mail.outbox = []

        webapi_token.save()

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        html_body = email.alternatives[0][0]
        partial_token = '%s...' % webapi_token.token[:10]

        self.assertEqual(email.subject, 'Review Board API token updated')
        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'], settings.SERVER_EMAIL)
        self.assertEqual(email.to[0], build_email_address_for_user(self.user))
        self.assertNotIn(webapi_token.token, email.body)
        self.assertNotIn(webapi_token.token, html_body)
        self.assertIn(partial_token, email.body)
        self.assertIn(partial_token, html_body)
        self.assertIn('One of your API tokens has been updated', email.body)
        self.assertIn('One of your API tokens has been updated', html_body)

    def test_delete_token(self):
        """Testing sending e-mail when an existing API Token is deleted"""
        webapi_token = WebAPIToken.objects.generate_token(user=self.user,
                                                          note='Test',
                                                          policy={})
        mail.outbox = []

        webapi_token.delete()

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        html_body = email.alternatives[0][0]

        self.assertEqual(email.subject, 'Review Board API token deleted')
        self.assertEqual(email.from_email, self.sender)
        self.assertEqual(email.extra_headers['From'], settings.SERVER_EMAIL)
        self.assertEqual(email.to[0], build_email_address_for_user(self.user))
        self.assertIn(webapi_token.token, email.body)
        self.assertIn(webapi_token.token, html_body)
        self.assertIn('One of your API tokens has been deleted', email.body)
        self.assertIn('One of your API tokens has been deleted', html_body)


class WebHookPayloadTests(SpyAgency, TestCase):
    """Tests for payload rendering."""

    ENDPOINT_URL = 'http://example.com/endpoint/'

    @add_fixtures(['test_scmtools', 'test_users'])
    def test_diffset_rendered(self):
        """Testing JSON-serializability of DiffSets in WebHook payloads"""
        self.spy_on(OpenerDirector.open, call_original=False)
        WebHookTarget.objects.create(url=self.ENDPOINT_URL,
                                     events='review_request_published')

        review_request = self.create_review_request(create_repository=True)
        self.create_diffset(review_request)
        review_request.publish(review_request.submitter)

        self.assertTrue(OpenerDirector.open.spy.called)

        self.create_diffset(review_request, draft=True)
        review_request.publish(review_request.submitter)
        self.assertEqual(len(OpenerDirector.open.spy.calls), 2)


class WebHookCustomContentTests(TestCase):
    """Unit tests for render_custom_content."""

    def test_with_valid_template(self):
        """Tests render_custom_content with a valid template"""
        s = render_custom_content(
            '{% if mybool %}{{s1}}{% else %}{{s2}}{% endif %}',
            {
                'mybool': True,
                's1': 'Hi!',
                's2': 'Bye!',
            })

        self.assertEqual(s, 'Hi!')

    def test_with_blocked_block_tag(self):
        """Tests render_custom_content with blocked {% block %}"""
        with self.assertRaisesMessage(TemplateSyntaxError,
                                      "Invalid block tag: 'block'"):
            render_custom_content('{% block foo %}{% endblock %})')

    def test_with_blocked_debug_tag(self):
        """Tests render_custom_content with blocked {% debug %}"""
        with self.assertRaisesMessage(TemplateSyntaxError,
                                      "Invalid block tag: 'debug'"):
            render_custom_content('{% debug %}')

    def test_with_blocked_extends_tag(self):
        """Tests render_custom_content with blocked {% extends %}"""
        with self.assertRaisesMessage(TemplateSyntaxError,
                                      "Invalid block tag: 'extends'"):
            render_custom_content('{% extends "base.html" %}')

    def test_with_blocked_include_tag(self):
        """Tests render_custom_content with blocked {% include %}"""
        with self.assertRaisesMessage(TemplateSyntaxError,
                                      "Invalid block tag: 'include'"):
            render_custom_content('{% include "base.html" %}')

    def test_with_blocked_load_tag(self):
        """Tests render_custom_content with blocked {% load %}"""
        with self.assertRaisesMessage(TemplateSyntaxError,
                                      "Invalid block tag: 'load'"):
            render_custom_content('{% load i18n %}')

    def test_with_blocked_ssi_tag(self):
        """Tests render_custom_content with blocked {% ssi %}"""
        with self.assertRaisesMessage(TemplateSyntaxError,
                                      "Invalid block tag: 'ssi'"):
            render_custom_content('{% ssi "foo.html" %}')

    def test_with_unknown_vars(self):
        """Tests render_custom_content with unknown variables"""
        s = render_custom_content('{{settings.DEBUG}};{{settings.DATABASES}}')
        self.assertEqual(s, ';')


class WebHookDispatchTests(SpyAgency, TestCase):
    """Unit tests for dispatching webhooks."""

    ENDPOINT_URL = 'http://example.com/endpoint/'

    def test_dispatch_custom_payload(self):
        """Test dispatch_webhook_event with custom payload"""
        custom_content = (
            '{\n'
            '{% for i in items %}'
            '  "item{{i}}": true{% if not forloop.last %},{% endif %}\n'
            '{% endfor %}'
            '}')
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON,
                                use_custom_content=True,
                                custom_content=custom_content)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'items': [1, 2, 3],
            },
            'application/json',
            ('{\n'
             '  "item1": true,\n'
             '  "item2": true,\n'
             '  "item3": true\n'
             '}'))

    def test_dispatch_non_ascii_custom_payload(self):
        """Testing dispatch_webhook_event with non-ASCII custom payload"""
        non_ascii_content = '{"sign": "{{sign|escapejs}}"}'

        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON,
                                use_custom_content=True,
                                custom_content=non_ascii_content)

        self._test_dispatch(
            handler,
            'my-event',
            {'sign': '\u00A4'},
            'application/json',
            '{"sign": "\u00A4"}'.encode('utf-8')
        )

    def test_dispatch_form_data(self):
        """Test dispatch_webhook_event with Form Data payload"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_FORM_DATA)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'items': [1, 2, 3],
            },
            'application/x-www-form-urlencoded',
            'payload=%7B%22items%22%3A+%5B1%2C+2%2C+3%5D%7D')

    def test_dispatch_non_ascii_form_data(self):
        """Testing dispatch_webhook_event with non-ASCII Form Data payload"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_FORM_DATA)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'sign': '\u00A4',
            },
            'application/x-www-form-urlencoded',
            'payload=%7B%22sign%22%3A+%22%5Cu00a4%22%7D')

    def test_dispatch_json(self):
        """Test dispatch_webhook_event with JSON payload"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'items': [1, 2, 3],
            },
            'application/json',
            '{"items": [1, 2, 3]}')

    def test_dispatch_non_ascii_json(self):
        """Testing dispatch_webhook_event with non-ASCII JSON payload"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'sign': '\u00A4',
            },
            'application/json',
            '{"sign": "\\u00a4"}')

    def test_dispatch_xml(self):
        """Test dispatch_webhook_event with XML payload"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_XML)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'items': [1, 2, 3],
            },
            'application/xml',
            ('<?xml version="1.0" encoding="utf-8"?>\n'
             '<rsp>\n'
             ' <items>\n'
             '  <array>\n'
             '   <item>1</item>\n'
             '   <item>2</item>\n'
             '   <item>3</item>\n'
             '  </array>\n'
             ' </items>\n'
             '</rsp>'))

    def test_dispatch_non_ascii_xml(self):
        """Testing dispatch_webhook_event with non-ASCII XML payload"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_XML)

        self._test_dispatch(
            handler,
            'my-event',
            {
                'sign': '\u00A4',
            },
            'application/xml',
            ('<?xml version="1.0" encoding="utf-8"?>\n'
             '<rsp>\n'
             ' <sign>\u00A4</sign>\n'
             '</rsp>').encode('utf-8'))

    def test_dispatch_with_secret(self):
        """Test dispatch_webhook_event with HMAC secret"""
        handler = WebHookTarget(events='my-event',
                                url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON,
                                secret='foobar123')

        self._test_dispatch(
            handler,
            'my-event',
            {
                'items': [1, 2, 3],
            },
            'application/json',
            '{"items": [1, 2, 3]}',
            'sha1=46f8529ef47da2291eeb475f0d0c0a6f58f88f8b')

    def test_dispatch_invalid_template(self):
        """Testing dispatch_webhook_event with an invalid template"""
        handler = WebHookTarget(events='my-event', url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON,
                                use_custom_content=True,
                                custom_content=r'{% invalid_block_tag %}')

        self.spy_on(logging.exception)
        self.spy_on(OpenerDirector.open,
                    call_fake=lambda *args, **kwargs: None)

        dispatch_webhook_event(FakeHTTPRequest(None), [handler], 'my-event',
                               None)

        self.assertFalse(OpenerDirector.open.spy.called)
        self.assertTrue(logging.exception.spy.called)
        self.assertIsInstance(logging.exception.spy.last_call.args[1],
                              TemplateSyntaxError)

    def test_dispatch_render_error(self):
        """Testing dispatch_webhook_event with an unencodable object"""
        class Unencodable(object):
            pass

        handler = WebHookTarget(events='my-event', url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON)

        self.spy_on(logging.exception)
        self.spy_on(OpenerDirector.open,
                    call_fake=lambda *args, **kwargs: None)

        dispatch_webhook_event(FakeHTTPRequest(None), [handler], 'my-event', {
            'unencodable': Unencodable(),
        })

        self.assertFalse(OpenerDirector.open.spy.called)
        self.assertTrue(logging.exception.spy.called)
        self.assertIsInstance(logging.exception.spy.last_call.args[1],
                              TypeError)

    def test_dispatch_cannot_open(self):
        """Testing dispatch_webhook_event with an unresolvable URL"""
        def _urlopen(opener, *args, **kwargs):
            raise IOError('')

        handler = WebHookTarget(events='my-event', url=self.ENDPOINT_URL,
                                encoding=WebHookTarget.ENCODING_JSON)

        self.spy_on(logging.exception)
        self.spy_on(OpenerDirector.open, call_fake=_urlopen)

        dispatch_webhook_event(FakeHTTPRequest(None), [handler, handler],
                               'my-event',
                               None)

        self.assertEqual(len(OpenerDirector.open.spy.calls), 2)
        self.assertTrue(len(logging.exception.spy.calls), 2)
        self.assertIsInstance(logging.exception.spy.calls[0].args[2], IOError)
        self.assertIsInstance(logging.exception.spy.calls[1].args[2], IOError)


    def _test_dispatch(self, handler, event, payload, expected_content_type,
                       expected_data, expected_sig_header=None):
        def _urlopen(opener, request):
            self.assertEqual(request.get_full_url(), self.ENDPOINT_URL)
            self.assertEqual(request.headers['X-reviewboard-event'], event)
            self.assertEqual(request.headers['Content-type'],
                             expected_content_type)
            self.assertEqual(request.data, expected_data)
            self.assertEqual(request.headers['Content-length'],
                             len(expected_data))

            if expected_sig_header:
                self.assertIn('X-hub-signature', request.headers)
                self.assertEqual(request.headers['X-hub-signature'],
                                 expected_sig_header)
            else:
                self.assertNotIn('X-hub-signature', request.headers)

            # Check that all sent data are binary strings.
            self.assertIsInstance(request.get_full_url(), six.binary_type)

            for h in request.headers:
                self.assertIsInstance(h, six.binary_type)
                self.assertNotIsInstance(request.headers[h], six.text_type)

            self.assertIsInstance(request.data, six.binary_type)

        self.spy_on(OpenerDirector.open, call_fake=_urlopen)

        # We need to ensure that logging.exception is not called
        # in order to avoid silent swallowing of test assertion failures
        self.spy_on(logging.exception)

        request = FakeHTTPRequest(None)
        dispatch_webhook_event(request, [handler], event, payload)

        # Assuming that if logging.exception is called, an assertion
        # error was raised - and should thus be raised further.
        if logging.exception.spy.called:
            raise logging.exception.spy.calls[0].args[2]


class WebHookTargetManagerTests(TestCase):
    """Unit tests for WebHookTargetManager."""
    ENDPOINT_URL = 'http://example.com/endpoint/'

    def test_for_event(self):
        """Testing WebHookTargetManager.for_event"""
        # These should not match.
        WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        WebHookTarget.objects.create(
            events='event3',
            url=self.ENDPOINT_URL,
            enabled=False,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        # These should match.
        target1 = WebHookTarget.objects.create(
            events='event2,event3',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        target2 = WebHookTarget.objects.create(
            events='*',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        targets = WebHookTarget.objects.for_event('event3')
        self.assertEqual(targets, [target1, target2])

    def test_for_event_with_local_site(self):
        """Testing WebHookTargetManager.for_event with Local Sites"""
        site = LocalSite.objects.create(name='test-site')

        # These should not match.
        WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=False,
            local_site=site,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        # This should match.
        target = WebHookTarget.objects.create(
            events='event1,event2',
            url=self.ENDPOINT_URL,
            enabled=True,
            local_site=site,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        targets = WebHookTarget.objects.for_event('event1',
                                                  local_site_id=site.pk)
        self.assertEqual(targets, [target])

    @add_fixtures(['test_scmtools'])
    def test_for_event_with_repository(self):
        """Testing WebHookTargetManager.for_event with repository"""
        repository1 = self.create_repository()
        repository2 = self.create_repository()

        # These should not match.
        unused_target1 = WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=False,
            apply_to=WebHookTarget.APPLY_TO_SELECTED_REPOS)
        unused_target1.repositories.add(repository2)

        unused_target2 = WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=False,
            apply_to=WebHookTarget.APPLY_TO_SELECTED_REPOS)
        unused_target2.repositories.add(repository1)

        WebHookTarget.objects.create(
            events='event3',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_NO_REPOS)

        # These should match.
        target1 = WebHookTarget.objects.create(
            events='event1,event2',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        target2 = WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_SELECTED_REPOS)
        target2.repositories.add(repository1)

        targets = WebHookTarget.objects.for_event('event1',
                                                  repository_id=repository1.pk)
        self.assertEqual(targets, [target1, target2])

    @add_fixtures(['test_scmtools'])
    def test_for_event_with_no_repository(self):
        """Testing WebHookTargetManager.for_event with no repository"""
        repository = self.create_repository()

        # These should not match.
        unused_target1 = WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_SELECTED_REPOS)
        unused_target1.repositories.add(repository)

        WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=False,
            apply_to=WebHookTarget.APPLY_TO_NO_REPOS)

        WebHookTarget.objects.create(
            events='event2',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_NO_REPOS)

        # These should match.
        target1 = WebHookTarget.objects.create(
            events='event1,event2',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_ALL)

        target2 = WebHookTarget.objects.create(
            events='event1',
            url=self.ENDPOINT_URL,
            enabled=True,
            apply_to=WebHookTarget.APPLY_TO_NO_REPOS)

        targets = WebHookTarget.objects.for_event('event1')
        self.assertEqual(targets, [target1, target2])

    def test_for_event_with_all_events(self):
        """Testing WebHookTargetManager.for_event with ALL_EVENTS"""
        with self.assertRaisesMessage(ValueError,
                                      '"*" is not a valid event choice'):
            WebHookTarget.objects.for_event(WebHookTarget.ALL_EVENTS)


class WebHookSignalDispatchTests(SpyAgency, TestCase):
    """Unit tests for dispatching webhooks by signals."""

    ENDPOINT_URL = 'http://example.com/endpoint/'

    fixtures = ['test_users']

    def setUp(self):
        super(WebHookSignalDispatchTests, self).setUp()

        self.spy_on(dispatch_webhook_event, call_original=False)

    def test_review_request_closed_submitted(self):
        """Testing webhook dispatch from 'review_request_closed' signal
        with submitted
        """
        target = WebHookTarget.objects.create(events='review_request_closed',
                                              url=self.ENDPOINT_URL)

        review_request = self.create_review_request(publish=True)
        review_request.close(review_request.SUBMITTED)

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_closed')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_closed')
        self.assertEqual(payload['closed_by']['id'],
                         review_request.submitter.pk)
        self.assertEqual(payload['close_type'], 'submitted')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_closed_submitted_local_site(self):
        """Testing webhook dispatch from 'review_request_closed' signal with
        submitted for a local site
        """
        local_site = LocalSite.objects.create(name='test-site')
        local_site.users.add(User.objects.get(username='doc'))

        target = WebHookTarget.objects.create(events='review_request_closed',
                                              url=self.ENDPOINT_URL,
                                              local_site=local_site)

        review_request = self.create_review_request(local_site=local_site,
                                                    publish=True)
        review_request.close(review_request.SUBMITTED)

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_closed')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_closed')
        self.assertEqual(payload['closed_by']['id'],
                         review_request.submitter.pk)
        self.assertEqual(payload['close_type'], 'submitted')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_closed_discarded(self):
        """Testing webhook dispatch from 'review_request_closed' signal
        with discarded
        """
        target = WebHookTarget.objects.create(events='review_request_closed',
                                              url=self.ENDPOINT_URL)

        review_request = self.create_review_request()
        review_request.close(review_request.DISCARDED)

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_closed')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_closed')
        self.assertEqual(payload['closed_by']['id'],
                         review_request.submitter.pk)
        self.assertEqual(payload['close_type'], 'discarded')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_closed_discarded_local_site(self):
        """Testing webhook dispatch from 'review_request_closed' signal with
        discarded for a local site
        """
        local_site = LocalSite.objects.create(name='test-site')
        local_site.users.add(User.objects.get(username='doc'))

        target = WebHookTarget.objects.create(events='review_request_closed',
                                              url=self.ENDPOINT_URL,
                                              local_site=local_site)

        review_request = self.create_review_request(local_site=local_site,
                                                    publish=True)
        review_request.close(review_request.DISCARDED)

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_closed')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_closed')
        self.assertEqual(payload['closed_by']['id'],
                         review_request.submitter.pk)
        self.assertEqual(payload['close_type'], 'discarded')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_published(self):
        """Testing webhook dispatch from 'review_request_published' signal"""
        target = WebHookTarget.objects.create(
            events='review_request_published',
            url=self.ENDPOINT_URL)

        review_request = self.create_review_request()
        review_request.publish(review_request.submitter)

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_published')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_published')
        self.assertIn('is_new', payload)
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_published_local_site(self):
        """Testing webhook dispatch from 'review_request_published' signal for
        a local site
        """
        local_site = LocalSite.objects.create(name='test-site')
        local_site.users.add(User.objects.get(username='doc'))

        target = WebHookTarget.objects.create(
            events='review_request_published', url=self.ENDPOINT_URL,
            local_site=local_site)

        review_request = self.create_review_request(local_site=local_site)
        review_request.publish(review_request.submitter)

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_published')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_published')
        self.assertIn('is_new', payload)
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_reopened(self):
        """Testing webhook dispatch from 'review_request_reopened' signal"""
        target = WebHookTarget.objects.create(
            events='review_request_reopened',
            url=self.ENDPOINT_URL)

        review_request = self.create_review_request(publish=True)
        review_request.close(review_request.SUBMITTED)
        review_request.reopen()

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_reopened')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_reopened')
        self.assertEqual(payload['reopened_by']['id'],
                         review_request.submitter.pk)
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_request_reopened_local_site(self):
        """Testing webhook dispatch from 'review_request_reopened' signal
        for a local site
        """
        local_site = LocalSite.objects.create(name='test-site')
        local_site.users.add(User.objects.get(username='doc'))

        target = WebHookTarget.objects.create(events='review_request_reopened',
                                              url=self.ENDPOINT_URL,
                                              local_site=local_site)

        review_request = self.create_review_request(local_site=local_site,
                                                    publish=True)
        review_request.close(review_request.SUBMITTED)
        review_request.reopen()

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_request_reopened')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_request_reopened')
        self.assertEqual(payload['reopened_by']['id'],
                         review_request.submitter.pk)
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)

    def test_review_published(self):
        """Testing webhook dispatch from 'review_published' signal"""
        target = WebHookTarget.objects.create(events='review_published',
                                              url=self.ENDPOINT_URL)

        review_request = self.create_review_request()
        review = self.create_review(review_request)
        review.publish()

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_published')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_published')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)
        self.assertEqual(payload['review']['id'], review.pk)
        self.assertIn('diff_comments', payload)
        self.assertIn('screenshot_comments', payload)
        self.assertIn('file_attachment_comments', payload)
        self.assertIn('general_comments', payload)

    def test_review_published_local_site(self):
        """Testing webhook dispatch from 'review_published' signal for a local
        site
        """
        local_site = LocalSite.objects.create(name='test-site')
        local_site.users.add(User.objects.get(username='doc'))

        target = WebHookTarget.objects.create(events='review_published',
                                              url=self.ENDPOINT_URL,
                                              local_site=local_site)

        review_request = self.create_review_request(local_site=local_site,
                                                    publish=True)
        review = self.create_review(review_request)
        review.publish()

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'review_published')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'review_published')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)
        self.assertEqual(payload['review']['id'], review.pk)
        self.assertIn('diff_comments', payload)
        self.assertIn('screenshot_comments', payload)
        self.assertIn('file_attachment_comments', payload)

    def test_reply_published(self):
        """Testing webhook dispatch from 'reply_published' signal"""
        target = WebHookTarget.objects.create(events='reply_published',
                                              url=self.ENDPOINT_URL)

        review_request = self.create_review_request()
        review = self.create_review(review_request)
        reply = self.create_reply(review)
        reply.publish()

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'reply_published')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'reply_published')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)
        self.assertEqual(payload['reply']['id'], reply.pk)
        self.assertIn('diff_comments', payload)
        self.assertIn('screenshot_comments', payload)
        self.assertIn('file_attachment_comments', payload)
        self.assertIn('general_comments', payload)

        # Test for bug 3999
        self.assertEqual(payload['reply']['links']['diff_comments']['href'],
                         'http://example.com/api/review-requests/1/reviews/1/'
                         'replies/2/diff-comments/')

    def test_reply_published_local_site(self):
        """Testing webhook dispatch from 'reply_published' signal for a local
        site
        """
        local_site = LocalSite.objects.create(name='test-site')
        local_site.users.add(User.objects.get(username='doc'))

        target = WebHookTarget.objects.create(events='reply_published',
                                              url=self.ENDPOINT_URL,
                                              local_site=local_site)

        review_request = self.create_review_request(local_site=local_site,
                                                    publish=True)
        review = self.create_review(review_request)
        reply = self.create_reply(review)
        reply.publish()

        spy = dispatch_webhook_event.spy
        self.assertTrue(spy.called)
        self.assertEqual(len(spy.calls), 1)

        last_call = spy.last_call
        self.assertEqual(last_call.args[1], [target])
        self.assertEqual(last_call.args[2], 'reply_published')

        payload = last_call.args[3]
        self.assertEqual(payload['event'], 'reply_published')
        self.assertEqual(payload['review_request']['id'],
                         review_request.display_id)
        self.assertEqual(payload['reply']['id'], reply.pk)
        self.assertIn('diff_comments', payload)
        self.assertIn('screenshot_comments', payload)
        self.assertIn('file_attachment_comments', payload)


class EmailUtilsTests(TestCase):
    """Testing e-mail utilities that do not send e-mails."""

    def test_recipients_to_addresses_with_string_address(self):
        """Testing generating addresses from recipients with string recipients
        """
        with self.assertRaises(AssertionError):
            recipients_to_addresses(['foo@example.com'])

    @add_fixtures(['test_users'])
    def test_recipients_to_addresses_with_users(self):
        """Testing generating addresses from recipients with user recipients
        """
        users = list(User.objects.filter(username__in=['doc', 'grumpy']))

        addresses = recipients_to_addresses(users)
        self.assertEqual(len(addresses), 2)

        expected_addresses = set(
            build_email_address_for_user(u)
            for u in users
        )

        self.assertEqual(addresses, expected_addresses)

    def test_recipients_to_addresses_with_groups_single_mailinglist(self):
        """Testing generating addresses from recipients that are groups with a
        single mailing list address
        """
        groups = [
            Group(name='group1', display_name='Group One',
                  mailing_list='group1@example.com'),
            Group(name='group2', display_name='Group Two',
                  mailing_list='group2@example.com'),
        ]

        addresses = recipients_to_addresses(groups)
        self.assertEqual(len(addresses), 2)

        expected_addresses = set(sum(
            (
                get_email_addresses_for_group(group)
                for group in groups
            ),
            []))

        self.assertEqual(addresses, expected_addresses)

    def test_recipients_to_addresses_with_groups_many_mailinglist(self):
        """Testing generating addresses from recipients that are groups with
        multiple mailing list addresses
        """
        groups = [
            Group(name='group1', display_name='Group One',
                  mailing_list='group1a@example.com,group1b@example.com'),
            Group(name='group2', display_name='Group Two',
                  mailing_list='group2a@example.com,group2b@example.com'),
        ]

        addresses = recipients_to_addresses(groups)
        self.assertEqual(len(addresses), 4)

        expected_addresses = set(sum(
            (
                get_email_addresses_for_group(group)
                for group in groups
            ),
            []))

        self.assertEqual(addresses, expected_addresses)

    @add_fixtures(['test_users'])
    def test_recipients_to_addresses_with_groups_and_users(self):
        """Testing generating addresses from recipients that are users and
        groups with mailing list addresses
        """
        groups = [
            Group(name='group1', display_name='Group One',
                  mailing_list='group1@example.com'),
            Group(name='group2', display_name='Group Two',
                  mailing_list='group2@example.com'),
        ]

        users = list(User.objects.filter(username__in=['doc', 'grumpy']).all())

        addresses = recipients_to_addresses(groups + users)
        self.assertEqual(len(addresses), 4)

        user_addresses = [
            build_email_address_for_user(u)
            for u in users
        ]

        group_addresses = sum(
            (
                get_email_addresses_for_group(group)
                for group in groups
            ),
            [])

        self.assertEqual(addresses,
                         set(user_addresses + group_addresses))

    def test_recipients_to_addresses_with_groups_with_members(self):
        """Testing generating addresses from recipients that are groups with
        no mailing list addresses
        """
        group1 = Group.objects.create(name='group1')
        group2 = Group.objects.create(name='group2')

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        group1.users = [user1]
        group2.users = [user2]

        addresses = recipients_to_addresses([group1, group2])

        expected_addresses = set([
            build_email_address_for_user(user1),
            build_email_address_for_user(user2),
        ])

        self.assertEqual(addresses, expected_addresses)

    def test_recipients_to_addresses_with_groups_local_site(self):
        """Testing generating addresses from recipients that are groups in
        local sites
        """
        local_site1 = LocalSite.objects.create(name='local-site1')
        local_site2 = LocalSite.objects.create(name='local-site2')

        group1 = Group.objects.create(name='group1', local_site=local_site1)
        group2 = Group.objects.create(name='group2', local_site=local_site2)

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        local_site1.users = [user1]

        group1.users = [user1]
        group2.users = [user2]

        addresses = recipients_to_addresses([group1, group2])
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses, set([build_email_address_for_user(user1)]))

    def test_recipients_to_addresses_with_groups_inactive_members(self):
        """Testing generating addresses form recipients that are groups with
        inactive members
        """
        group1 = self.create_review_group('group1')
        group2 = self.create_review_group('group2')

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        group1.users = [user1]
        group2.users = [user2]

        addresses = recipients_to_addresses([group1, group2])
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses, set([build_email_address_for_user(user1)]))

    def test_recipients_to_addresses_groups_local_site_inactive_members(self):
        """Testing generating addresses from recipients that are groups in
        local sites that have inactive members
        """
        local_site1 = LocalSite.objects.create(name='local-site1')
        local_site2 = LocalSite.objects.create(name='local-site2')

        group1 = self.create_review_group('group1', local_site=local_site1)
        group2 = self.create_review_group('group2', local_site=local_site2)

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        local_site1.users = [user1]
        local_site2.users = [user2]

        group1.users = [user1]
        group2.users = [user2]

        addresses = recipients_to_addresses([group1, group2])
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses, set([build_email_address_for_user(user1)]))

    @add_fixtures(['test_users'])
    def test_build_recipients_user_receive_email(self):
        """Testing building recipients for a review request where the user
        wants to receive e-mail
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([submitter]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_user_not_receive_email(self):
        """Testing building recipients for a review request where the user
        does not want to receive e-mail
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        profile = submitter.get_profile()
        profile.should_send_email = False
        profile.save()

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(len(to), 0)
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_user_not_receive_own_email(self):
        """Testing building recipients for a review request where the user
        does not want to receive e-mail about their updates
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        profile = submitter.get_profile()
        profile.should_send_own_updates = False
        profile.save()

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(len(to), 0)
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_not_receive_own_email(self):
        """Testing building recipieints for a review request where the
        submitter is a reviewer and doesn't want to receive e-mail about their
        updates
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        review_request.target_people = [submitter]

        profile = submitter.get_profile()
        profile.should_send_own_updates = False
        profile.save()

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(len(to), 0)
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipient_user_not_receive_own_email(self):
        """Testing building recipients for a review request where the
        submitter is a reviewer and doesn't want to receive e-mail about their
        updates
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        profile = submitter.get_profile()
        profile.should_send_own_updates = False
        profile.save()

        to, cc = build_recipients(submitter, review_request, [submitter])

        self.assertEqual(len(to), 0)
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_and_groups(self):
        """Testing building recipients for a review request where there are
        target users and groups
        """
        group = self.create_review_group()
        user = User.objects.get(username='grumpy')

        review_request = self.create_review_request()
        review_request.target_people = [user]
        review_request.target_groups = [group]

        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([user]))
        self.assertEqual(cc, set([submitter, group]))

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_inactive_and_groups(self):
        """Testing building recipients for a review request where there are
        target groups and inactive target users
        """
        group = self.create_review_group()
        user = User.objects.create(username='user', first_name='User',
                                   last_name='Foo', is_active=False)

        review_request = self.create_review_request()
        review_request.target_people = [user]
        review_request.target_groups = [group]

        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([submitter, group]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_target_groups(self):
        """Testing build recipients for a review request where there are target
        groups
        """
        group1 = self.create_review_group('group1')
        group2 = self.create_review_group('group2')

        review_request = self.create_review_request()
        review_request.target_groups = [group1, group2]
        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(len(to), 3)
        self.assertEqual(to, set([submitter, group1, group2]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people(self):
        """Testing building recipients for a review request with target people
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        grumpy = User.objects.get(username='grumpy')
        review_request.target_people = [grumpy]

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([grumpy]))
        self.assertEqual(cc, set([submitter]))

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_inactive(self):
        """Testing building recipients for a review request with target people
        who are inactive
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        review_request.target_people = [user1, user2]

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([user1]))
        self.assertEqual(cc, set([submitter]))

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_no_email(self):
        """Testing building recipients for a review request with target people
        who don't receive e-mail
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        Profile.objects.create(user=user2, should_send_email=False)

        review_request.target_people = [user1, user2]

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([user1]))
        self.assertEqual(cc, set([submitter]))

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_local_site(self):
        """Testing building recipients for a review request where the target
        people are in local sites
        """
        local_site = LocalSite.objects.create(name=self.local_site_name)

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        local_site.users = [user1]

        review_request = self.create_review_request(with_local_site=True)
        review_request.target_people = [user1, user2]

        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([user1]))
        self.assertEqual(cc, set([submitter]))

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_local_site_inactive(self):
        """Testing building recipients for a review request where the target
        people are in local sites and are inactive
        """
        local_site = LocalSite.objects.create(name=self.local_site_name)

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        local_site.users = [user1, user2]

        review_request = self.create_review_request(with_local_site=True)
        review_request.target_people = [user1, user2]

        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([user1]))
        self.assertEqual(cc, set([submitter]))

    @add_fixtures(['test_users'])
    def test_build_recipients_target_people_local_site_no_email(self):
        """Testing building recipients for a review request where the target
        people are in local sites don't receieve e-mail
        """
        local_site = LocalSite.objects.create(name=self.local_site_name)

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        Profile.objects.create(user=user2,
                               should_send_email=False)

        local_site.users = [user1, user2]

        review_request = self.create_review_request(with_local_site=True)
        review_request.target_people = [user1, user2]

        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([user1]))
        self.assertEqual(cc, set([submitter]))

    @add_fixtures(['test_users'])
    def test_build_recipients_limit_to(self):
        """Testing building recipients with a limited recipients list"""
        dopey = User.objects.get(username='dopey')
        grumpy = User.objects.get(username='grumpy')
        group = self.create_review_group()

        review_request = self.create_review_request()
        submitter = review_request.submitter

        review_request.target_people = [dopey]
        review_request.target_groups = [group]

        to, cc = build_recipients(submitter, review_request,
                                  limit_recipients_to=[grumpy])

        self.assertEqual(to, set([submitter, grumpy]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_limit_to_inactive(self):
        """Testing building recipients with a limited recipients list that
        contains inactive users
        """
        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        review_request = self.create_review_request()
        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request,
                                  limit_recipients_to=[user1, user2])

        self.assertEqual(to, set([submitter, user1]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_limit_to_local_site(self):
        """Testing building recipients with a limited recipients list that
        contains users in local sites
        """
        local_site1 = LocalSite.objects.create(name='local-site1')
        local_site2 = LocalSite.objects.create(name='local-site2')

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        local_site1.users = [user1]
        local_site2.users = [user2]

        review_request = self.create_review_request(local_site=local_site1)
        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request,
                                  limit_recipients_to=[user1, user2])

        self.assertEqual(to, set([submitter, user1]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipients(self):
        """Testing building recipients with an extra recipients list"""
        review_request = self.create_review_request()
        submitter = review_request.submitter

        grumpy = User.objects.get(username='grumpy')

        to, cc = build_recipients(submitter, review_request,
                                  extra_recipients=[grumpy])

        self.assertEqual(to, set([submitter, grumpy]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipients_inactive(self):
        """Testing building recipients with an extra recipients list that
        contains inactive users
        """
        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        review_request = self.create_review_request()
        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request,
                                  extra_recipients=[user1, user2])

        self.assertEqual(to, set([submitter, user1]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipients_local_site(self):
        """Testing building recipients with an extra recipients list that
        contains users in local sites
        """
        local_site1 = LocalSite.objects.create(name='local-site1')
        local_site2 = LocalSite.objects.create(name='local-site2')

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        local_site1.users = [user1]
        local_site2.users = [user2]

        review_request = self.create_review_request(local_site=local_site1)
        submitter = review_request.submitter

        to, cc = build_recipients(submitter, review_request,
                                  extra_recipients=[user1, user2])

        self.assertEqual(to, set([submitter, user1]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipients_and_limit_to(self):
        """Testing building recipients with an extra recipients list and
        a limited recipients list
        """
        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')
        user3 = User.objects.create(username='user3', first_name='User',
                                    last_name='Three')

        group = self.create_review_group()

        review_request = self.create_review_request()
        submitter = review_request.submitter
        review_request.target_people = [user3]
        review_request.target_groups = [group]

        to, cc = build_recipients(submitter, review_request,
                                  extra_recipients=[user1],
                                  limit_recipients_to=[user2])

        self.assertEqual(to, set([submitter, user2]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipients_and_limit_to_inactive(self):
        """Testing building recipients with an extra recipients list and a
        limited recipients list that contains inactive users
        """
        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)
        user3 = User.objects.create(username='user3', first_name='User',
                                    last_name='Three')

        group = self.create_review_group()

        review_request = self.create_review_request()
        submitter = review_request.submitter
        review_request.target_people = [user3]
        review_request.target_groups = [group]

        to, cc = build_recipients(submitter, review_request,
                                  extra_recipients=[user1],
                                  limit_recipients_to=[user2])

        self.assertEqual(to, set([submitter]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_extra_recipients_and_limit_to_local_site(self):
        """Testing building recipients with an extra recipients list and a
        limited recipients list that contains users in local sites
        """
        local_site1 = LocalSite.objects.create(name='local-site1')
        local_site2 = LocalSite.objects.create(name='local-site2')

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')
        user3 = User.objects.create(username='user3', first_name='User',
                                    last_name='Three')

        local_site1.users = [user1, user3]
        local_site2.users = [user2]

        group = self.create_review_group()

        review_request = self.create_review_request(local_site=local_site1)
        submitter = review_request.submitter
        review_request.target_people = [user3]
        review_request.target_groups = [group]

        to, cc = build_recipients(submitter, review_request,
                                  extra_recipients=[user1],
                                  limit_recipients_to=[user2])

        self.assertEqual(to, set([submitter]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_starred(self):
        """Testing building recipients where the review request has been
        starred by a user
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        grumpy = User.objects.get(username='grumpy')
        profile = grumpy.get_profile()
        profile.starred_review_requests = [review_request]
        profile.save()

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([submitter, grumpy]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_starred_inactive(self):
        """Testing building recipients where the review request has been
        starred by users that may be inactive
        """
        review_request = self.create_review_request()
        submitter = review_request.submitter

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two', is_active=False)

        profile1 = Profile.objects.create(user=user1)
        profile1.starred_review_requests = [review_request]

        profile2 = Profile.objects.create(user=user2)
        profile2.starred_review_requests = [review_request]

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([submitter, user1]))
        self.assertEqual(len(cc), 0)

    @add_fixtures(['test_users'])
    def test_build_recipients_starred_local_site(self):
        """Testing building recipients where the review request has been
        starred by users that are in local sites
        """
        local_site1 = LocalSite.objects.create(name='local-site1')
        local_site2 = LocalSite.objects.create(name='local-site2')

        review_request = self.create_review_request(local_site=local_site1)
        submitter = review_request.submitter

        user1 = User.objects.create(username='user1', first_name='User',
                                    last_name='One')
        user2 = User.objects.create(username='user2', first_name='User',
                                    last_name='Two')

        local_site1.users = [user1]
        local_site2.users = [user2]

        profile1 = Profile.objects.create(user=user1)
        profile1.starred_review_requests = [review_request]

        profile2 = Profile.objects.create(user=user2)
        profile2.starred_review_requests = [review_request]

        to, cc = build_recipients(submitter, review_request)

        self.assertEqual(to, set([submitter, user1]))
        self.assertEqual(len(cc), 0)


class BasePreviewEmailViewTests(TestCase):
    """Unit tests for BasePreviewEmailView."""

    @override_settings(DEBUG=True)
    def test_get_with_classmethod(self):
        """Testing BasePreviewEmailView.get with build_email as classmethod"""
        class MyPreviewEmailView(BasePreviewEmailView):
            @classmethod
            def build_email(cls, test_var):
                self.assertEqual(test_var, 'test')
                return EmailMessage(subject='Test Subject',
                                    text_body='Test Body')

            def get_email_data(view, request, test_var=None, *args, **kwargs):
                self.assertEqual(test_var, 'test')

                return {
                    'test_var': test_var,
                }

        request = RequestFactory().request()
        request.user = User.objects.create(username='test-user')

        view = MyPreviewEmailView.as_view()
        response = view(request, test_var='test', message_format='text')

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=True)
    def test_get_with_staticmethod(self):
        """Testing BasePreviewEmailView.get with build_email as staticmethod"""
        class MyPreviewEmailView(BasePreviewEmailView):
            @staticmethod
            def build_email(test_var):
                self.assertEqual(test_var, 'test')
                return EmailMessage(subject='Test Subject',
                                    text_body='Test Body')

            def get_email_data(view, request, test_var=None, *args, **kwargs):
                self.assertEqual(test_var, 'test')

                return {
                    'test_var': test_var,
                }

        request = RequestFactory().request()
        request.user = User.objects.create(username='test-user')

        view = MyPreviewEmailView.as_view()
        response = view(request, test_var='test', message_format='text')

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False)
    def test_get_with_debug_false(self):
        """Testing BasePreviewEmailView.get with DEBUG=False"""
        class MyPreviewEmailView(BasePreviewEmailView):
            @classmethod
            def build_email(cls, test_var):
                self.fail('build_email should not be reached')
                return EmailMessage(subject='Test Subject',
                                    text_body='Test Body')

            def get_email_data(view, request, test_var=None, *args, **kwargs):
                self.fail('get_email_data should not be reached')

        request = RequestFactory().request()
        request.user = User.objects.create(username='test-user')

        view = MyPreviewEmailView.as_view()

        with self.assertRaises(Http404):
            view(request, test_var='test', message_format='text')
