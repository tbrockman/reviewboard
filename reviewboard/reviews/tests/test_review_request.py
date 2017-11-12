from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.utils import six
from djblets.testing.decorators import add_fixtures
from kgb import SpyAgency

from reviewboard.changedescs.models import ChangeDescription
from reviewboard.reviews.errors import PublishError
from reviewboard.reviews.models import (Comment, ReviewRequest,
                                        ReviewRequestDraft)
from reviewboard.reviews.signals import (review_request_reopened,
                                         review_request_reopening)
from reviewboard.scmtools.core import ChangeSet
from reviewboard.testing import TestCase


class ReviewRequestTests(SpyAgency, TestCase):
    """Tests for reviewboard.reviews.models.ReviewRequest."""

    fixtures = ['test_users']

    def test_public_with_discard_reopen_submitted(self):
        """Testing ReviewRequest.public when discarded, reopened, submitted"""
        review_request = self.create_review_request(publish=True)
        self.assertTrue(review_request.public)

        review_request.close(ReviewRequest.DISCARDED)
        self.assertTrue(review_request.public)

        review_request.reopen()
        self.assertFalse(review_request.public)

        review_request.publish(review_request.submitter)

        review_request.close(ReviewRequest.SUBMITTED)
        self.assertTrue(review_request.public)

    def test_close_removes_commit_id(self):
        """Testing ReviewRequest.close with discarded removes commit ID"""
        review_request = self.create_review_request(publish=True,
                                                    commit_id='123')
        self.assertEqual(review_request.commit_id, '123')
        review_request.close(ReviewRequest.DISCARDED)

        self.assertIsNone(review_request.commit_id)

    def test_reopen_from_discarded(self):
        """Testing ReviewRequest.reopen from discarded review request"""
        review_request = self.create_review_request(publish=True)
        self.assertTrue(review_request.public)

        review_request.close(ReviewRequest.DISCARDED)

        self.spy_on(review_request_reopened.send)
        self.spy_on(review_request_reopening.send)

        review_request.reopen(user=review_request.submitter)

        self.assertFalse(review_request.public)
        self.assertEqual(review_request.status, ReviewRequest.PENDING_REVIEW)

        draft = review_request.get_draft()
        changedesc = draft.changedesc
        self.assertEqual(changedesc.fields_changed['status']['old'][0],
                         ReviewRequest.DISCARDED)
        self.assertEqual(changedesc.fields_changed['status']['new'][0],
                         ReviewRequest.PENDING_REVIEW)

        # Test that the signals were emitted correctly.
        self.assertTrue(review_request_reopening.send.spy.last_called_with(
            sender=ReviewRequest,
            user=review_request.submitter,
            review_request=review_request))
        self.assertTrue(review_request_reopened.send.spy.last_called_with(
            sender=ReviewRequest,
            user=review_request.submitter,
            review_request=review_request,
            old_status=ReviewRequest.DISCARDED,
            old_public=True))

    def test_reopen_from_submitted(self):
        """Testing ReviewRequest.reopen from submitted review request"""
        review_request = self.create_review_request(publish=True)
        self.assertTrue(review_request.public)

        review_request.close(ReviewRequest.SUBMITTED)

        self.spy_on(review_request_reopened.send)
        self.spy_on(review_request_reopening.send)

        review_request.reopen(user=review_request.submitter)

        self.assertTrue(review_request.public)
        self.assertEqual(review_request.status, ReviewRequest.PENDING_REVIEW)

        changedesc = review_request.changedescs.latest()
        self.assertEqual(changedesc.fields_changed['status']['old'][0],
                         ReviewRequest.SUBMITTED)
        self.assertEqual(changedesc.fields_changed['status']['new'][0],
                         ReviewRequest.PENDING_REVIEW)

        self.assertTrue(review_request_reopening.send.spy.last_called_with(
            sender=ReviewRequest,
            user=review_request.submitter,
            review_request=review_request))
        self.assertTrue(review_request_reopened.send.spy.last_called_with(
            sender=ReviewRequest,
            user=review_request.submitter,
            review_request=review_request,
            old_status=ReviewRequest.SUBMITTED,
            old_public=True))

    def test_changenum_against_changenum_and_commit_id(self):
        """Testing create ReviewRequest with changenum against both changenum
        and commit_id
        """
        changenum = 123
        review_request = self.create_review_request(publish=True,
                                                    changenum=changenum)
        review_request = ReviewRequest.objects.get(pk=review_request.id)
        self.assertEqual(review_request.changenum, changenum)
        self.assertIsNone(review_request.commit_id)

    @add_fixtures(['test_scmtools'])
    def test_changeset_update_commit_id(self):
        """Testing ReviewRequest.changeset_is_pending update commit ID
        behavior
        """
        current_commit_id = '123'
        new_commit_id = '124'
        review_request = self.create_review_request(
            publish=True,
            commit_id=current_commit_id,
            create_repository=True)
        draft = ReviewRequestDraft.create(review_request)
        self.assertEqual(review_request.commit_id, current_commit_id)
        self.assertEqual(draft.commit_id, current_commit_id)

        def _get_fake_changeset(scmtool, commit_id, allow_empty=True):
            self.assertEqual(commit_id, current_commit_id)

            changeset = ChangeSet()
            changeset.pending = False
            changeset.changenum = int(new_commit_id)
            return changeset

        scmtool = review_request.repository.get_scmtool()
        scmtool.supports_pending_changesets = True
        self.spy_on(scmtool.get_changeset,
                    call_fake=_get_fake_changeset)

        self.spy_on(review_request.repository.get_scmtool,
                    call_fake=lambda x: scmtool)

        is_pending, new_commit_id = \
            review_request.changeset_is_pending(current_commit_id)
        self.assertEqual(is_pending, False)
        self.assertEqual(new_commit_id, new_commit_id)

        review_request = ReviewRequest.objects.get(pk=review_request.pk)
        self.assertEqual(review_request.commit_id, new_commit_id)

        draft = review_request.get_draft()
        self.assertEqual(draft.commit_id, new_commit_id)

    def test_unicode_summary_and_str(self):
        """Testing ReviewRequest.__str__ with unicode summaries."""
        review_request = self.create_review_request(
            summary='\u203e\u203e', publish=True)
        self.assertEqual(six.text_type(review_request), '\u203e\u203e')

    def test_discard_unpublished_private(self):
        """Testing ReviewRequest.close with private requests on discard
        to ensure changes from draft are copied over
        """
        review_request = self.create_review_request(
            publish=False,
            public=False)

        self.assertFalse(review_request.public)
        self.assertNotEqual(review_request.status, ReviewRequest.DISCARDED)

        draft = ReviewRequestDraft.create(review_request)

        summary = 'Test summary'
        description = 'Test description'
        testing_done = 'Test testing done'

        draft.summary = summary
        draft.description = description
        draft.testing_done = testing_done
        draft.save()

        review_request.close(ReviewRequest.DISCARDED)

        self.assertEqual(review_request.summary, summary)
        self.assertEqual(review_request.description, description)
        self.assertEqual(review_request.testing_done, testing_done)

    def test_discard_unpublished_public(self):
        """Testing ReviewRequest.close with public requests on discard
        to ensure changes from draft are not copied over
        """
        review_request = self.create_review_request(
            publish=False,
            public=True)

        self.assertTrue(review_request.public)
        self.assertNotEqual(review_request.status, ReviewRequest.DISCARDED)

        draft = ReviewRequestDraft.create(review_request)

        summary = 'Test summary'
        description = 'Test description'
        testing_done = 'Test testing done'

        draft.summary = summary
        draft.description = description
        draft.testing_done = testing_done
        draft.save()

        review_request.close(ReviewRequest.DISCARDED)

        self.assertNotEqual(review_request.summary, summary)
        self.assertNotEqual(review_request.description, description)
        self.assertNotEqual(review_request.testing_done, testing_done)

    def test_publish_changedesc_none(self):
        """Testing ReviewRequest.publish on a new request to ensure there are
        no change descriptions
        """
        review_request = self.create_review_request(publish=True)

        review_request.publish(review_request.submitter)

        with self.assertRaises(ChangeDescription.DoesNotExist):
            review_request.changedescs.filter(public=True).latest()

    def test_submit_nonpublic(self):
        """Testing ReviewRequest.close with non-public requests to ensure state
        transitions to SUBMITTED from non-public review request is not allowed
        """
        review_request = self.create_review_request(public=False)

        with self.assertRaises(PublishError):
            review_request.close(ReviewRequest.SUBMITTED)

    def test_submit_public(self):
        """Testing ReviewRequest.close with public requests to ensure
        public requests can be transferred to SUBMITTED
        """
        review_request = self.create_review_request(public=True)

        review_request.close(ReviewRequest.SUBMITTED)

    def test_determine_user_for_review_request(self):
        """Testing ChangeDescription.get_user for change descriptions for
        review requests
        """
        review_request = self.create_review_request(publish=True)
        doc = review_request.submitter
        grumpy = User.objects.get(username='grumpy')

        change1 = ChangeDescription()
        change1.record_field_change('foo', ['bar'], ['baz'])
        change1.save()
        review_request.changedescs.add(change1)

        change2 = ChangeDescription()
        change2.record_field_change('submitter', doc, grumpy, 'username')
        change2.save()
        review_request.changedescs.add(change2)

        change3 = ChangeDescription()
        change3.record_field_change('foo', ['bar'], ['baz'])
        change3.save()
        review_request.changedescs.add(change3)

        change4 = ChangeDescription()
        change4.record_field_change('submitter', grumpy, doc, 'username')
        change4.save()
        review_request.changedescs.add(change4)

        self.assertIsNone(change1.user)
        self.assertIsNone(change2.user)
        self.assertIsNone(change3.user)
        self.assertIsNone(change4.user)

        self.assertEqual(change1.get_user(review_request), doc)
        self.assertEqual(change2.get_user(review_request), doc)
        self.assertEqual(change3.get_user(review_request), grumpy)
        self.assertEqual(change4.get_user(review_request), grumpy)

        self.assertEqual(change1.user, doc)
        self.assertEqual(change2.user, doc)
        self.assertEqual(change3.user, grumpy)
        self.assertEqual(change4.user, grumpy)


class IssueCounterTests(TestCase):
    """Unit tests for review request issue counters."""

    fixtures = ['test_users']

    def setUp(self):
        super(IssueCounterTests, self).setUp()

        self.review_request = self.create_review_request(publish=True)
        self.assertEqual(self.review_request.issue_open_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

        self._reset_counts()

    @add_fixtures(['test_scmtools'])
    def test_init_with_diff_comments(self):
        """Testing ReviewRequest issue counter initialization from diff
        comments
        """
        self.review_request.repository = self.create_repository()

        diffset = self.create_diffset(self.review_request)
        filediff = self.create_filediff(diffset)

        self._test_issue_counts(
            lambda review, issue_opened: self.create_diff_comment(
                review, filediff, issue_opened=issue_opened))

    def test_init_with_file_attachment_comments(self):
        """Testing ReviewRequest issue counter initialization from file
        attachment comments
        """
        file_attachment = self.create_file_attachment(self.review_request)

        self._test_issue_counts(
            lambda review, issue_opened: self.create_file_attachment_comment(
                review, file_attachment, issue_opened=issue_opened))

    def test_init_with_general_comments(self):
        """Testing ReviewRequest issue counter initialization from general
        comments
        """
        self._test_issue_counts(
            lambda review, issue_opened: self.create_general_comment(
                review, issue_opened=issue_opened))

    def test_init_with_screenshot_comments(self):
        """Testing ReviewRequest issue counter initialization from screenshot
        comments
        """
        screenshot = self.create_screenshot(self.review_request)

        self._test_issue_counts(
            lambda review, issue_opened: self.create_screenshot_comment(
                review, screenshot, issue_opened=issue_opened))

    @add_fixtures(['test_scmtools'])
    def test_init_with_mix(self):
        """Testing ReviewRequest issue counter initialization from multiple
        types of comments at once
        """
        # The initial implementation for issue status counting broke when
        # there were multiple types of comments on a review (such as diff
        # comments and file attachment comments). There would be an
        # artificially large number of issues reported.
        #
        # That's been fixed, and this test is ensuring that it doesn't
        # regress.
        self.review_request.repository = self.create_repository()
        diffset = self.create_diffset(self.review_request)
        filediff = self.create_filediff(diffset)
        file_attachment = self.create_file_attachment(self.review_request)
        screenshot = self.create_screenshot(self.review_request)

        review = self.create_review(self.review_request)

        # One open file attachment comment
        self.create_file_attachment_comment(review, file_attachment,
                                            issue_opened=True)

        # Two diff comments
        self.create_diff_comment(review, filediff, issue_opened=True)
        self.create_diff_comment(review, filediff, issue_opened=True)

        # Four screenshot comments
        self.create_screenshot_comment(review, screenshot, issue_opened=True)
        self.create_screenshot_comment(review, screenshot, issue_opened=True)
        self.create_screenshot_comment(review, screenshot, issue_opened=True)
        self.create_screenshot_comment(review, screenshot, issue_opened=True)

        # Three open general comments
        self.create_general_comment(review, issue_opened=True)
        self.create_general_comment(review, issue_opened=True)
        self.create_general_comment(review, issue_opened=True)

        # The issue counts should be end up being 0, since they'll initialize
        # during load.
        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

        # Now publish. We should have 10 open issues, by way of incrementing
        # during publish.
        review.publish()

        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 10)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

        # Make sure we get the same number back when initializing counters.
        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 10)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

    def test_init_file_attachment_comment_with_replies(self):
        """Testing ReviewRequest file attachment comment issue counter
        initialization and replies
        """
        file_attachment = self.create_file_attachment(self.review_request)

        review = self.create_review(self.review_request)
        comment = self.create_file_attachment_comment(review, file_attachment,
                                                      issue_opened=True)
        review.publish()

        reply = self.create_reply(review)
        self.create_file_attachment_comment(reply, file_attachment,
                                            reply_to=comment,
                                            issue_opened=True)
        reply.publish()

        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

    def test_init_general_comment_with_replies(self):
        """Testing ReviewRequest general comment issue counter initialization
        and replies
        """
        review = self.create_review(self.review_request)
        comment = self.create_general_comment(review, issue_opened=True)
        review.publish()

        reply = self.create_reply(review)
        self.create_general_comment(reply, reply_to=comment,
                                    issue_opened=True)
        reply.publish()

        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

    def test_save_reply_comment_to_file_attachment_comment(self):
        """Testing ReviewRequest file attachment comment issue counter and
        saving reply comments
        """
        file_attachment = self.create_file_attachment(self.review_request)

        review = self.create_review(self.review_request)
        comment = self.create_file_attachment_comment(review, file_attachment,
                                                      issue_opened=True)
        review.publish()

        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

        reply = self.create_reply(review)
        reply_comment = self.create_file_attachment_comment(
            reply, file_attachment,
            reply_to=comment,
            issue_opened=True)
        reply.publish()

        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

        reply_comment.save()
        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

    def test_save_reply_comment_to_general_comment(self):
        """Testing ReviewRequest general comment issue counter and saving
        reply comments.
        """
        review = self.create_review(self.review_request)
        comment = self.create_general_comment(review, issue_opened=True)
        review.publish()

        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

        reply = self.create_reply(review)
        reply_comment = self.create_general_comment(
            reply, reply_to=comment, issue_opened=True)
        reply.publish()

        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

        reply_comment.save()
        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 1)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)

    def _test_issue_counts(self, create_comment_func):
        review = self.create_review(self.review_request)

        # One comment without an issue opened.
        create_comment_func(review, issue_opened=False)

        # One comment without an issue opened, which will have its
        # status set to a valid status, while closed.
        closed_with_status_comment = \
            create_comment_func(review, issue_opened=False)

        # Three comments with an issue opened.
        for i in range(3):
            create_comment_func(review, issue_opened=True)

        # Two comments that will have their issues dropped.
        dropped_comments = [
            create_comment_func(review, issue_opened=True)
            for i in range(2)
        ]

        # One comment that will have its issue resolved.
        resolved_comments = [
            create_comment_func(review, issue_opened=True)
        ]

        # One comment will be in Verifying Dropped mode.
        verify_dropped_comments = [
            create_comment_func(review, issue_opened=True)
        ]

        # Two comments will be in Verifying Resolved mode.
        verify_resolved_comments = [
            create_comment_func(review, issue_opened=True)
            for i in range(2)
        ]

        # The issue counts should be end up being 0, since they'll initialize
        # during load.
        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

        # Now publish. We should have 6 open issues, by way of incrementing
        # during publish.
        review.publish()

        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 9)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

        # Make sure we get the same number back when initializing counters.
        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 9)
        self.assertEqual(self.review_request.issue_dropped_count, 0)
        self.assertEqual(self.review_request.issue_resolved_count, 0)
        self.assertEqual(self.review_request.issue_verifying_count, 0)

        # Set the issue statuses.
        for comment in dropped_comments:
            comment.issue_status = Comment.DROPPED
            comment.save()

        for comment in resolved_comments:
            comment.issue_status = Comment.RESOLVED
            comment.save()

        for comment in verify_resolved_comments:
            comment.issue_status = Comment.VERIFYING_RESOLVED
            comment.save()

        for comment in verify_dropped_comments:
            comment.issue_status = Comment.VERIFYING_DROPPED
            comment.save()

        closed_with_status_comment.issue_status = Comment.OPEN
        closed_with_status_comment.save()

        self._reload_object()
        self.assertEqual(self.review_request.issue_open_count, 3)
        self.assertEqual(self.review_request.issue_dropped_count, 2)
        self.assertEqual(self.review_request.issue_resolved_count, 1)
        self.assertEqual(self.review_request.issue_verifying_count, 3)

        # Make sure we get the same number back when initializing counters.
        self._reload_object(clear_counters=True)
        self.assertEqual(self.review_request.issue_open_count, 3)
        self.assertEqual(self.review_request.issue_dropped_count, 2)
        self.assertEqual(self.review_request.issue_resolved_count, 1)
        self.assertEqual(self.review_request.issue_verifying_count, 3)

    def _reload_object(self, clear_counters=False):
        if clear_counters:
            # 3 queries: One for the review request fetch, one for
            # the issue status load, and one for updating the issue counts.
            expected_query_count = 3
            self._reset_counts()
        else:
            # One query for the review request fetch.
            expected_query_count = 1

        with self.assertNumQueries(expected_query_count):
            self.review_request = \
                ReviewRequest.objects.get(pk=self.review_request.pk)

    def _reset_counts(self):
        self.review_request.issue_open_count = None
        self.review_request.issue_resolved_count = None
        self.review_request.issue_dropped_count = None
        self.review_request.issue_verifying_count = None
        self.review_request.save()


class ApprovalTests(TestCase):
    """Unit tests for ReviewRequest approval logic."""

    fixtures = ['test_users']

    def setUp(self):
        super(ApprovalTests, self).setUp()

        self.review_request = self.create_review_request(publish=True)

    def test_approval_states_ship_it(self):
        """Testing ReviewRequest default approval logic with Ship It"""
        self.create_review(self.review_request, ship_it=True, publish=True)

        self.assertTrue(self.review_request.approved)
        self.assertIsNone(self.review_request.approval_failure)

    def test_approval_states_no_ship_its(self):
        """Testing ReviewRequest default approval logic with no Ship-Its"""
        self.create_review(self.review_request, ship_it=False, publish=True)

        self.assertFalse(self.review_request.approved)
        self.assertEqual(self.review_request.approval_failure,
                         'The review request has not been marked "Ship It!"')

    def test_approval_states_open_issues(self):
        """Testing ReviewRequest default approval logic with open issues"""
        review = self.create_review(self.review_request, ship_it=True)
        self.create_general_comment(review, issue_opened=True)
        review.publish()

        self.review_request.reload_issue_open_count()

        self.assertFalse(self.review_request.approved)
        self.assertEqual(self.review_request.approval_failure,
                         'The review request has open issues.')

    def test_approval_states_unverified_issues(self):
        """Testing ReviewRequest default approval logic with unverified issues
        """
        review = self.create_review(self.review_request, ship_it=True)
        comment = self.create_general_comment(review, issue_opened=True)
        review.publish()

        comment.issue_status = Comment.VERIFYING_RESOLVED
        comment.save()

        self.review_request.reload_issue_open_count()
        self.review_request.reload_issue_verifying_count()

        self.assertFalse(self.review_request.approved)
        self.assertEqual(self.review_request.approval_failure,
                         'The review request has unverified issues.')
