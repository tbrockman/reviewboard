/**
 * Handles all operations and state related to editing review requests.
 *
 * This manages the editing of all fields and objects on a review request,
 * the publishing workflow, and validation.
 */
RB.ReviewRequestEditor = Backbone.Model.extend({
    defaults: {
        changeDescriptionRenderedText: '',
        closeDescriptionRenderedText: '',
        commentIssueManager: null,
        editable: false,
        editCount: 0,
        hasDraft: false,
        fileAttachments: null,
        fileAttachmentComments: {},
        mutableByUser: false,
        pendingSaveCount: 0,
        publishing: false,
        reviewRequest: null,
        screenshots: null,
        showSendEmail: false,
        statusEditable: false,
        statusMutableByUser: false,
    },

    /**
     * Initialize the editor.
     */
    initialize() {
        const reviewRequest = this.get('reviewRequest');

        // Set up file attachments.
        let fileAttachments = this.get('fileAttachments');

        if (fileAttachments === null) {
            fileAttachments = new Backbone.Collection([], {
                model: RB.FileAttachment,
            });
            this.set('fileAttachments', fileAttachments);
        }

        this.listenTo(fileAttachments, 'add',
                      this._onFileAttachmentOrScreenshotAdded);
        fileAttachments.each(
            this._onFileAttachmentOrScreenshotAdded.bind(this));

        // Set up screenshots.
        let screenshots = this.get('screenshots');

        if (screenshots === null) {
            screenshots = new Backbone.Collection([], {
                model: RB.Screenshot,
            });
            this.set('screenshots', screenshots);
        }

        this.listenTo(screenshots, 'add',
                      this._onFileAttachmentOrScreenshotAdded);
        screenshots.each(
            this._onFileAttachmentOrScreenshotAdded.bind(this));

        // Connect to other signals.
        this.listenTo(reviewRequest.draft, 'saving',
                      () => this.trigger('saving'));
        this.listenTo(reviewRequest.draft, 'saved',
                      () => this.trigger('saved'));
        this.listenTo(reviewRequest, 'change:state', this._computeEditable);
        this._computeEditable();
    },

    /**
     * Create a file attachment tracked by the editor.
     *
     * This wraps RB.ReviewRequestDraft.createFileAttachment and stores the
     * file attachment in the fileAttachments collection.
     *
     * This should be used instead of
     * RB.ReviewRequestDraft.createFileAttachment for any existing or newly
     * uploaded file attachments.
     *
     * Args:
     *     attributes (object):
     *         Model attributes for the new file attachment.
     *
     * Returns:
     *     RB.FileAttachment:
     *     The new file attachment model.
     */
    createFileAttachment(attributes) {
        const draft = this.get('reviewRequest').draft;
        const fileAttachments = this.get('fileAttachments');
        const fileAttachment = draft.createFileAttachment(attributes);

        fileAttachments.add(fileAttachment);

        return fileAttachment;
    },

    /**
     * Return a field from the draft.
     *
     * This will look either in the draft's data or in the extraData (for
     * custom fields), returning the value provided either when the page
     * was generated or when it was last edited.
     *
     * Args:
     *     fieldName (string):
     *         The name of the field to get.
     *
     *     options (object, optional):
     *         Options for the operation.
     *
     * Option Args:
     *     useExtraData (boolean):
     *         Whether the field is stored as part of the extraData or is a
     *         regular attribute.
     *
     * Returns:
     *     *:
     *     The value of the field.
     */
    getDraftField(fieldName, options={}) {
        const reviewRequest = this.get('reviewRequest');
        const draft = reviewRequest.draft;

        if (options.useExtraData) {
            return draft.get('extraData')[fieldName];
        } else if (fieldName === 'closeDescription' ||
                   fieldName === 'closeDescriptionRichText') {
            return reviewRequest.get(fieldName);
        } else {
            return draft.get(fieldName);
        }
    },

    /**
     * Set a field in the draft.
     *
     * If we're in the process of publishing, this will check if we have saved
     * all fields before publishing the draft.
     *
     * Once the field has been saved, two events will be triggered:
     *
     *     * fieldChanged(fieldName, value)
     *     * fieldChanged:<fieldName>(value)
     *
     * Args:
     *     fieldName (string):
     *         The name of the field to set.
     *
     *     value (*):
     *         The value to set in the field.
     *
     *     options (object, optional):
     *         Options for the set operation.
     *
     *     context (object, optional):
     *         Optional context to use when calling callbacks.
     *
     * Option Args:
     *     allowMarkdown (boolean, optional):
     *         Whether the field can support rich text (Markdown).
     *
     *     error (function, optional):
     *         A callback to call in case of error.
     *
     *     jsonFieldName (string, optional):
     *         The key to use for the field name in the API.
     *
     *     jsonTextTypeFieldName (string, optional):
     *         The key to use for the name of the field indicating the text
     *         type (rich text or plain) in the API.
     *
     *     richText (boolean, optional):
     *         Whether the field is rich text (Markdown) formatted.
     *
     *     success (function, optional):
     *         A callback to call once the field has been set successfully.
     *
     *     useExtraData (boolean, optional):
     *         Whether the field should be set as a key in extraData or as a
     *         direct attribute.
     */
    setDraftField: function(fieldName, value, options={}, context=undefined) {
        const reviewRequest = this.get('reviewRequest');
        const data = {};

        let jsonFieldName = options.jsonFieldName;

        if (options.useExtraData) {
            jsonFieldName = `extra_data.${jsonFieldName}`;
        }

        if (options.allowMarkdown) {
            let jsonTextTypeFieldName = options.jsonTextTypeFieldName;

            if (options.useExtraData) {
                jsonTextTypeFieldName = `extra_data.${jsonTextTypeFieldName}`;
            }

            const richText = !!options.richText;
            data[jsonTextTypeFieldName] = richText ? 'markdown' : 'plain';

            data.force_text_type = 'html';
            data.include_text_types = 'raw';
        }

        data[jsonFieldName] = value;

        reviewRequest.draft.save({
            data: data,
            error: (model, xhr) => {
                let message = '';

                this.set('publishing', false);

                if (_.isFunction(options.error)) {
                    const rsp = xhr.errorPayload;
                    const fieldValue = rsp.fields[jsonFieldName];
                    const fieldValueLen = fieldValue.length;

                    /* Wrap each term in quotes or a leading 'and'. */
                    _.each(fieldValue, (value, i) => {
                        // XXX: This method isn't localizable.
                        if (i === fieldValueLen - 1 && fieldValueLen > 1) {
                            if (i > 2) {
                                message += ', ';
                            }

                            message += ` and "${value}"`;
                        } else {
                            if (i > 0) {
                                message += ', ';
                            }

                            message += `"${value}"`;
                        }
                    });

                    if (fieldName === 'targetGroups') {
                        message = interpolate(
                            ngettext('Group %s does not exist.',
                                     'Groups %s do not exist.',
                                     fieldValue.length),
                            [message]);
                    } else if (fieldName === 'targetPeople') {
                        message = interpolate(
                            ngettext('User %s does not exist.',
                                     'Users %s do not exist.',
                                     fieldValue.length),
                            [message]);
                    } else if (fieldName === 'submitter') {
                        message = interpolate(
                            gettext('User %s does not exist.'),
                            [message]);
                    } else if (fieldName === 'dependsOn') {
                        message = interpolate(
                            ngettext('Review Request %s does not exist.',
                                     'Review Requests %s do not exist.',
                                     fieldValue.length),
                            [message]);
                    }

                    options.error.call(context, {
                        errorText: message
                    });
                }
            },
            success: () => {
                this.set('hasDraft', true);

                if (_.isFunction(options.success)) {
                    options.success.call(context);
                }

                this.trigger('fieldChanged:' + fieldName, value);
                this.trigger('fieldChanged', fieldName, value);

                if (this.get('publishing')) {
                    this.decr('pendingSaveCount');

                    if (this.get('pendingSaveCount') === 0) {
                        this.set('publishing', false);
                        this.publishDraft();
                    }
                }
            }
        }, this);
    },

    /**
     * Publish the draft to the server.
     *
     * This assumes all fields have been saved.
     *
     * If there's an error during saving or validation, the "publishError"
     * event will be triggered with the error message. Otherwise, upon
     * success, the "publish" event will be triggered. However, users will
     * have the chance to cancel the publish in the event that the submitter
     * has been changed.
     *
     * Args:
     *     options (object):
     *         Options for the publish operation.
     *
     * Option Args:
     *     trivial (boolean):
     *         Whether the publish is "trivial" (if true, no e-mail
     *         notifications will be sent).
     */
    publishDraft(options={}) {
        const reviewRequest = this.get('reviewRequest');
        const onError = (model, xhr) => this.trigger('publishError', xhr.errorText);

        reviewRequest.draft.ensureCreated({
            success: () => {
                if (reviewRequest.attributes.links.submitter.title !==
                    reviewRequest.draft.attributes.links.submitter.title) {
                    if (!confirm(gettext('Are you sure you want to change the ownership of this review request? Doing so may prevent you from editing the review request afterwards.'))) {
                        return;
                    }
                }
                reviewRequest.draft.publish({
                    success: () => this.trigger('published'),
                    error: onError,
                    trivial: options.trivial ? 1 : 0
                }, this);
            },
            error: onError,
        }, this);
    },

    /**
     * Increment an attribute by 1.
     *
     * The attribute must be an integer.
     *
     * Args:
     *     attr (string):
     *         The name of the attribute to increment.
     */
    incr(attr) {
        const value = this.get(attr);
        console.assert(_.isNumber(value));
        this.set(attr, value + 1, {
            validate: true,
        });
    },

    /**
     * Decrement an attribute by 1.
     *
     * The attribute must be an integer.
     *
     * Args:
     *     attr (string):
     *         The name of the attribute to decrement.
     */
    decr(attr) {
        const value = this.get(attr);
        console.assert(_.isNumber(value));
        this.set(attr, value - 1, {
            validate: true,
        });
    },

    /**
     * Validate the given attributes.
     *
     * Args:
     *     attrs (object):
     *         The attributes to validate.
     */
    validate(attrs) {
        const strings = RB.ReviewRequestEditor.strings;

        if (_.has(attrs, 'editCount') && attrs.editCount < 0) {
            return strings.UNBALANCED_EDIT_COUNT;
        }
    },

    /**
     * Compute the editable state of the review request and open/close states.
     *
     * The review request is editable if the user has edit permissions and it's
     * not closed.
     *
     * The close state and accompanying description is editable if the user
     * has the ability to close the review request and it's currently closed.
     */
    _computeEditable() {
        const state = this.get('reviewRequest').get('state');
        const pending = (state === RB.ReviewRequest.PENDING);

        this.set({
            editable: this.get('mutableByUser') && pending,
            statusEditable: this.get('statusMutableByUser') && !pending,
        });
    },

    /**
     * Handle when a FileAttachment or Screenshot is added.
     *
     * Listens for events on the FileAttachment or Screenshot and relays
     * them to the editor.
     *
     * Args:
     *     attachment (RB.FileAttachment or RB.Screenshot):
     *         The new file attachment or screenshot.
     */
    _onFileAttachmentOrScreenshotAdded(attachment) {
        this.listenTo(attachment, 'saving',
                      () => this.trigger('saving'));

        this.listenTo(attachment, 'saved destroy', () => {
            this.set('hasDraft', true);
            this.trigger('saved');
        });
    },
}, {
    strings: {
        UNBALANCED_EDIT_COUNT:
            gettext('There is an internal error balancing the edit count'),
    },
});
