/**
 * Provides state and utility functions for loading and reviewing diffs.
 *
 * Model Attributes:
 *     fileDiffID (number):
 *         The ID of the FileDiff.
 *
 *     file (RB.DiffFile):
 *         Information on the file associated with this diff.
 *
 *     interdiffRevision (number):
 *         The revision on the end of an interdiff range.
 *
 *     interFileDiffID (number):
 *         The ID of the FileDiff on the end of an interdiff range.
 *
 *     revision (number):
 *         The revision of the FileDiff.
 */
RB.DiffReviewable = RB.AbstractReviewable.extend({
    defaults: _.defaults({
        file: null,
        fileDiffID: null,
        interdiffRevision: null,
        interFileDiffID: null,
        revision: null,
    }, RB.AbstractReviewable.prototype.defaults),

    commentBlockModel: RB.DiffCommentBlock,
    defaultCommentBlockFields: ['fileDiffID', 'interFileDiffID'],

    /**
     * Load a serialized comment and add comment blocks for it.
     *
     * Args:
     *     serializedCommentBlock (object):
     *         The serialized data for the new comment block(s).
     */
    loadSerializedCommentBlock(serializedCommentBlock) {
        this.createCommentBlock({
            reviewRequest: this.get('reviewRequest'),
            review: this.get('review'),
            fileDiffID: this.get('fileDiffID'),
            interFileDiffID: this.get('interFileDiffID'),
            beginLineNum: serializedCommentBlock.linenum,
            endLineNum: serializedCommentBlock.linenum +
                        serializedCommentBlock.num_lines - 1,
            serializedComments: serializedCommentBlock.comments || [],
        });
    },

    /**
     * Return the rendered diff for a file.
     *
     * The rendered file will be fetched from the server and eventually
     * returned as the argument to the success callback.
     *
     * Args:
     *     callbacks (object):
     *         The functions used to fetch the corresponding diff fragments.
     *
     *     context (object):
     *         The context passed to each callback function.
     *
     *     options (object, optional):
     *         The option arguments that control the behavior of this function.
     *
     * Option Args:
     *     showDeleted (boolean):
     *         Determines whether or not we want to requeue the corresponding
     *         diff in order to show its deleted content.
     */
    getRenderedDiff(callbacks, context, options={}) {
        let url = this._buildRenderedDiffURL() + '?index=' +
                  this.get('file').get('index');

        if (options.showDeleted) {
            url += '&show-deleted=1';
        }

        if (window.innerWidth <= 720) {
            url += '&view=top-down';
        }

        url += '&' + TEMPLATE_SERIAL;

        this._fetchFragment({
            url: url,
            noActivityIndicator: true,
        }, callbacks, context);
    },

    /**
     * Return a rendered fragment of a diff.
     *
     * The fragment will be fetched from the server and eventually returned
     * as the argument to the success callback.
     *
     * Args:
     *     options (object):
     *         The option arguments that control the behavior of this function.
     *
     *     callbacks (object):
     *         The functions used to fetch the corresponding diff fragments.
     *
     *     context (object):
     *         The context passed to each callback function.
     *
     * Option Args:
     *     chunkIndex (string):
     *         The chunk index to load.
     */
    getRenderedDiffFragment(options, callbacks, context) {
        console.assert(options.chunkIndex !== undefined,
                       'chunkIndex must be provided');

        this._fetchFragment({
            url: `${this._buildRenderedDiffURL()}chunk/${options.chunkIndex}/`,
            data: {
                'index': this.get('file').get('index'),
                'lines-of-context': options.linesOfContext,
                'view': window.innerWidth <= 720 ? 'top-down' : 'side-by-side',
            }
        }, callbacks, context);
    },

    /**
     * Fetch the diff fragment from the server.
     *
     * This is used internally by getRenderedDiff and getRenderedDiffFragment
     * to do all the actual fetching and calling of callbacks.
     *
     * Args:
     *     options (object):
     *         The option arguments that control the behavior of this function.
     *
     *     callbacks (object):
     *         The functions used to fetch the corresponding diff fragments.
     *
     *     context (object):
     *         The context passed to each callback function.
     */
    _fetchFragment(options, callbacks, context) {
        RB.apiCall(_.defaults(
            {
                type: 'GET',
                dataType: 'html'
            },
            options,
            _.bindCallbacks(callbacks, context)
        ));
    },

    /**
     * Return a URL that forms the base of a diff fragment fetch.
     *
     * Returns:
     *     string:
     *     The URL for fetching diff fragments.
     */
    _buildRenderedDiffURL() {
        const interdiffRevision = this.get('interdiffRevision');
        const interFileDiffID = this.get('interFileDiffID');
        let revisionStr = this.get('revision');

        if (interdiffRevision) {
            revisionStr += '-' + interdiffRevision;
        }

        return this.get('reviewRequest').get('reviewURL') + 'diff/' +
               revisionStr + '/fragment/' + this.get('fileDiffID') +
               (interFileDiffID ? '-' + interFileDiffID : '') +
               '/';
    },
});
