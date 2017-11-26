from __future__ import unicode_literals

from django.core.exceptions import ObjectDoesNotExist
from djblets.util.decorators import augment_method_from
from djblets.webapi.decorators import (webapi_login_required,
                                       webapi_response_errors,
                                       webapi_request_fields)
from djblets.webapi.errors import (DOES_NOT_EXIST, INVALID_FORM_DATA,
                                   NOT_LOGGED_IN, PERMISSION_DENIED)

from reviewboard.webapi.decorators import webapi_check_local_site

from reviewboard.webapi.resources import resources
from reviewboard.webapi.resources.base_file_attachment_comment import \
    BaseFileAttachmentCommentResource
from reviewboard.webapi.resources.review_file_attachment_comment import \
    ReviewFileAttachmentCommentResource


class ReviewReplyFileAttachmentCommentResource(
        BaseFileAttachmentCommentResource):
    """Provides information on replies to file comments made on a
    review reply.

    If the reply is a draft, then comments can be added, deleted, or
    changed on this list. However, if the reply is already published,
    then no changed can be made.
    """
    added_in = '1.6'

    allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')
    policy_id = 'review_reply_file_attachment_comment'
    model_parent_key = 'review'
    fields = dict({
        'reply_to': {
            'type': ReviewFileAttachmentCommentResource,
            'description': 'The comment being replied to.',
        },
    }, **BaseFileAttachmentCommentResource.fields)

    mimetype_list_resource_name = 'review-reply-file-attachment-comments'
    mimetype_item_resource_name = 'review-reply-file-attachment-comment'

    def get_queryset(self, request, review_id, reply_id, *args, **kwargs):
        q = super(ReviewReplyFileAttachmentCommentResource, self).get_queryset(
            request, *args, **kwargs)
        q = q.filter(review=reply_id, review__base_reply_to=review_id)
        return q

    @webapi_check_local_site
    @webapi_login_required
    @webapi_response_errors(DOES_NOT_EXIST, INVALID_FORM_DATA,
                            NOT_LOGGED_IN, PERMISSION_DENIED)
    @webapi_request_fields(
        required=
            BaseFileAttachmentCommentResource.REPLY_REQUIRED_CREATE_FIELDS,
        optional=
            BaseFileAttachmentCommentResource.REPLY_OPTIONAL_CREATE_FIELDS,
        allow_unknown=True
    )
    def create(self, request, reply_to_id, *args, **kwargs):
        """Creates a reply to a file comment on a review.

        This will create a reply to a file comment on a review.
        The new comment will contain the same dimensions of the comment
        being replied to, but may contain new text.

        Extra data can be stored later lookup. See
        :ref:`webapi2.0-extra-data` for more information.
        """
        try:
            resources.review_request.get_object(request, *args, **kwargs)
            reply = resources.review_reply.get_object(request, *args, **kwargs)
        except ObjectDoesNotExist:
            return DOES_NOT_EXIST

        if not resources.review_reply.has_modify_permissions(request, reply):
            return self.get_no_access_error(request)

        try:
            comment = resources.review_file_attachment_comment.get_object(
                request,
                comment_id=reply_to_id,
                *args, **kwargs)
        except ObjectDoesNotExist:
            return INVALID_FORM_DATA, {
                'fields': {
                    'reply_to_id': ['This is not a valid file comment ID'],
                }
            }

        return self.create_or_update_comment_reply(
            request=request,
            comment=comment,
            reply=reply,
            comments_m2m=reply.file_attachment_comments,
            default_attrs={
                'file_attachment': comment.file_attachment,
            },
            *args,
            **kwargs)

    @webapi_check_local_site
    @webapi_login_required
    @webapi_response_errors(DOES_NOT_EXIST, NOT_LOGGED_IN, PERMISSION_DENIED)
    @webapi_request_fields(
        optional=
            BaseFileAttachmentCommentResource.REPLY_OPTIONAL_UPDATE_FIELDS,
        allow_unknown=True
    )
    def update(self, request, *args, **kwargs):
        """Updates a reply to a file comment.

        This can only update the text in the comment. The comment being
        replied to cannot change.

        Extra data can be stored later lookup. See
        :ref:`webapi2.0-extra-data` for more information.
        """
        try:
            resources.review_request.get_object(request, *args, **kwargs)
            reply = resources.review_reply.get_object(request, *args, **kwargs)
            file_comment = self.get_object(request, *args, **kwargs)
        except ObjectDoesNotExist:
            return DOES_NOT_EXIST

        return self.update_comment(request=request,
                                   review=reply,
                                   comment=file_comment,
                                   is_reply=True,
                                   **kwargs)

    @augment_method_from(BaseFileAttachmentCommentResource)
    def delete(self, *args, **kwargs):
        """Deletes a file comment from a draft reply.

        This will remove the comment from the reply. This cannot be undone.

        Only comments on draft replies can be deleted. Attempting to delete
        a published comment will return a Permission Denied error.

        Instead of a payload response, this will return :http:`204`.
        """
        pass

    @augment_method_from(BaseFileAttachmentCommentResource)
    def get(self, *args, **kwargs):
        """Returns information on a reply to a file comment.

        Much of the information will be identical to that of the comment
        being replied to.
        """
        pass

    @augment_method_from(BaseFileAttachmentCommentResource)
    def get_list(self, *args, **kwargs):
        """Returns the list of replies to file comments made on a review reply.
        """
        pass


review_reply_file_attachment_comment_resource = \
    ReviewReplyFileAttachmentCommentResource()
