from __future__ import unicode_literals

from django.contrib.auth.models import User

from djblets.siteconfig.models import SiteConfiguration
from djblets.testing.decorators import add_fixtures

from reviewboard.attachments.tests import BaseFileAttachmentTestCase
from reviewboard.reviews.models import ReviewRequest
from reviewboard.testing import TestCase


class DiffFragmentViewTests(TestCase):
    """Tests for reviewboard.diffviewer.views.DiffFragmentView"""

    fixtures = ['test_users', 'test_scmtools', 'test_site']

    def setUp(self):
        super(DiffFragmentViewTests, self).setUp()
        self.siteconfig = SiteConfiguration.objects.get_current()
        self.siteconfig.set('auth_require_sitewide_login', False)
        self.siteconfig.save()
        self.user = User.objects.get(username='doc')
        self.review_request = self.create_review_request(create_repository=True,
                                                         publish=True,
                                                         submitter=self.user)
        self.diffset = self.create_diffset(self.review_request, revision=1)
        self.filediff = self.create_filediff(
                             self.diffset,
                             source_file='/diffutils.py',
                             dest_file='/diffutils.py',
                             source_revision='6bba278',
                             dest_detail='465d217',
                             diff=(
                                 b'diff --git a/diffutils.py b/diffutils.py\n'
                                 b'index 6bba278..465d217 100644\n'
                                 b'--- a/diffutils.py\n'
                                 b'+++ b/diffutils.py\n'
                                 b'@@ -1,3 +1,4 @@\n'
                                 b'+# diffutils.py\n'
                                 b' import fnmatch\n'
                                 b' import os\n'
                                 b' import re\n'))
        self.review_request.publish(self.user)
        self.client.login(username='doc', password='doc')

    def test_returns_side_by_side_by_default(self):
        """Testing desktop diff fragment template used by default"""
        response = self.client.get('/r/%d/diff/1/fragment/%s/'
                                   % (self.review_request.pk, self.filediff.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="sidebyside"')
        self.assertFalse(response.context['is_mobile'])

    def test_returns_top_down_with_query(self):
        """Testing mobile diff fragment template returned w/ ?view=top-down"""
        response = self.client.get('/r/%d/diff/1/fragment/%s/?view=top-down'
                                   % (self.review_request.pk, self.filediff.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="topdown"')
        self.assertTrue(response.context['is_mobile'])

    def test_returns_side_by_side_with_query(self):
        """Testing desktop diff fragment template w/ ?view=side-by-side"""
        response = self.client.get('/r/%d/diff/1/fragment/%s/?view=side-by-side'
                                   % (self.review_request.pk, self.filediff.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="sidebyside"')
        self.assertFalse(response.context['is_mobile'])

    def test_top_down_single_download_button(self):
        """Testing that top-down only renders one download button"""
        response = self.client.get('/r/%d/diff/1/fragment/%s/?view=top-down'
                                   % (self.review_request.pk, self.filediff.pk))
        self.assertEqual(response.status_code, 200)
        print response.content
        self.assertTrue(response.context['is_mobile'])
        self.assertContains(response,
                            'href="/r/%d/diff/1/download/%s/new/"'
                            % (self.review_request.pk, self.filediff.pk))
        self.assertNotContains(response,
                            'href="/r/%d/diff/1/download/%s/orig/"'
                            % (self.review_request.pk, self.filediff.pk))
