/*
 * Displays the file index for the diffs on a page.
 *
 * The file page lists the names of the files, as well as a little graph
 * icon showing the relative size and complexity of a file, a list of chunks
 * (and their types), and the number of lines added and removed.
 */
RB.DiffFileIndexView = Backbone.View.extend({
    chunkTemplate: _.template(
        '<a href="#<%= chunkID %>" class="<%= className %>"> </a>'
    ),

    events: {
        'click .clickable-row ': '_onAnchorClicked'
    },

    stats: {
        totalInserts: 0,
        totalDeletes: 0,
        totalReplaces: 0,
        totalFiles: 0,
    },

    loadedItems: [],

    /*
     * Initializes the view.
     */
    initialize: function() {
        this._$items = null;
        this._$itemsTable = null;

        this.collection = this.options.collection;
        this.listenTo(this.collection, 'update', this.update);
    },

    /*
     * Renders the view to the page.
     */
    render: function() {
        this.$el.empty();
        this._$itemsTable = $('<table/>').appendTo(this.$el);
        this._$items = this.$('tr');
        // Add the files from the collection

        this.update();

        return this;
    },

    _itemTemplate: _.template([
        '<tr class="clickable-row loading<%',
        ' if (newfile) { print(" new-file"); }',
        ' if (binary) { print(" binary-file"); }',
        ' if (deleted) { print(" deleted-file"); }',
        ' if (destFilename !== depotFilename) { print(" renamed-file"); }',
        ' %>">',
        ' <td class="diff-file-icon">',
        '  <span class="fa fa-spinner fa-pulse"></span>',
        ' </td>',
        ' <td class="diff-file-info">',
        '  <a href="#<%- index %>"><%- destFilename %></a>',
        '  <% if (destFilename !== depotFilename) { %>',
        '  <span class="diff-file-rename"><%- wasText %></span>',
        '  <% } %>',
        ' </td>',
        ' <td class="diff-chunks-cell">',
        '  <% if (binary) { %>',
        '   <%- binaryFileText %>',
        '  <% } else if (deleted) { %>',
        '   <%- deletedFileText %>',
        '  <% } else { %>',
        '   <div class="diff-chunks"></div>',
        '  <% } %>',
        ' </td>',
        '</tr>'
    ].join('')),

    /*
     * Update the list of files in the index view.
     */
    update: function() {
        this._$itemsTable.empty();
        this.collection.each(function(file) {
            this._$itemsTable.append(this._itemTemplate(
                _.defaults({
                    binaryFileText: gettext('Binary file'),
                    deletedFileText: gettext('Deleted'),
                    wasText: interpolate(gettext('Was %s'),
                                         [file.get('depotFilename')])
                }, file.attributes)
            ));
        }, this);
        this._$items = this.$('tr');
    },

    /*
     * Adds a loaded diff to the index.
     *
     * The reserved entry for the diff will be populated with a link to the
     * diff, and information about the diff.
     */
    addDiff: function(index, diffReviewableView) {
        var $item = $(this._$items[index])
            .removeClass('loading');
        this.loadedItems.push(index);

        if (diffReviewableView.$el.hasClass('diff-error')) {
            this._renderDiffError($item);
        } else {
            this._renderDiffEntry($item, diffReviewableView);
        }
    },

    /*
     * Renders a diff loading error.
     *
     * An error icon will be displayed in place of the typical complexity
     * icon.
     */
    _renderDiffError: function($item) {
        var $fileIcon = $item.find('.diff-file-icon');

        $fileIcon
            .html('<div class="rb-icon rb-icon-warning" />')
            .attr('title',
                  gettext('There was an error loading this diff. See the details below.'));
    },

    accumulateStats: function(fileStatistics) {
        this.stats.totalInserts += fileStatistics.numInserts;
        this.stats.totalDeletes += fileStatistics.numDeletes;
        this.stats.totalReplaces += fileStatistics.numReplaces;
        this.stats.totalFiles += 1;
        if (!this.diff_statistics) {
            // store the dom elements so we don't have to re-query
            var parent = $("#diff_statistics");
            this.diff_statistics = {
                parent: parent,
                lines_added: parent.find(".lines-added-text"),
                lines_changed: parent.find(".lines-changed-text"),
                lines_removed: parent.find(".lines-removed-text"),
                files_changed: parent.find(".files-changed-text"),
            };
        }
        if (this.diff_statistics) {
            this.diff_statistics.lines_added.text(this.stats.totalInserts + " lines added");
            this.diff_statistics.lines_changed.text(this.stats.totalReplaces + " lines modified");
            this.diff_statistics.lines_removed.text(this.stats.totalDeletes + " lines removed");
            this.diff_statistics.files_changed.text(this.stats.totalFiles + " files in diff");
        }
    },

    calculateFileStats: function($item, diffReviewableView, fileDeleted, fileAdded) {
        var $table = diffReviewableView.$el,
            linesEqual = $table.data('lines-equal'),
            numDeletes = 0,
            numInserts = 0,
            numReplaces = 0,
            chunksList = [];

        if (fileAdded) {
            numInserts = 1;
        } else if (fileDeleted) {
            numDeletes = 1;
        } else if ($item.hasClass('binary-file')) {
            numReplaces = 1;
        } else {
            _.each($table.children('tbody'), function(chunk) {
                var numRows = chunk.rows.length,
                    $chunk = $(chunk);

                if ($chunk.hasClass('delete')) {
                    numDeletes += numRows;
                } else if ($chunk.hasClass('insert')) {
                    numInserts += numRows;
                } else if ($chunk.hasClass('replace')) {
                    numReplaces += numRows;
                } else {
                    return;
                }

                chunksList.push(this.chunkTemplate({
                    chunkID: chunk.id.substr(5),
                    className: chunk.className
                }));
            }, this);

            /* Add clickable blocks for each diff chunk. */
            $item.find('.diff-chunks').html(chunksList.join(''));
        }
        return {
            'linesEqual': linesEqual,
            'numInserts': numInserts,
            'numDeletes': numDeletes,
            'numReplaces': numReplaces,
            'totalLines': linesEqual + numDeletes + numInserts + numReplaces,
            'chunksList': chunksList,
        }
    },
    /*
     * Renders the display of a loaded diff.
     */
    _renderDiffEntry: function($item, diffReviewableView) {
        var iconView,
        tooltip = '',
        tooltipParts = [],
        $fileIcon = $item.find('.diff-file-icon'),
        fileDeleted = $item.hasClass('deleted-file'),
        fileAdded = $item.hasClass('new-file'),
        fileStatistics = this.calculateFileStats($item, diffReviewableView, fileDeleted, fileAdded);
        this.accumulateStats(fileStatistics);

        /* Render the complexity icon. */
        iconView = new RB.DiffComplexityIconView({
            numInserts: fileStatistics.numInserts,
            numDeletes: fileStatistics.numDeletes,
            numReplaces: fileStatistics.numReplaces,
            totalLines: fileStatistics.totalLines
        });
        $fileIcon
            .empty()
            .append(iconView.$el);
        iconView.render();
        /* Add tooltip for icon */
        if (fileAdded) {
            tooltip = gettext('New file');
        } else if (fileDeleted) {
            tooltip = gettext('Deleted file');
        } else {
            if (fileStatistics.numInserts > 0) {
                tooltipParts.push(interpolate(
                    ngettext('%s new line', '%s new lines', fileStatistics.numInserts),
                    [fileStatistics.numInserts]));
            }

            if (fileStatistics.numReplaces > 0) {
                tooltipParts.push(interpolate(
                    ngettext('%s line changed', '%s lines changed', fileStatistics.numReplaces),
                    [fileStatistics.numReplaces]));
            }

            if (fileStatistics.numDeletes > 0) {
                tooltipParts.push(interpolate(
                    ngettext('%s line removed', '%s lines removed', fileStatistics.numDeletes),
                    [fileStatistics.numDeletes]));
            }

            tooltip = tooltipParts.join(', ');
        }

        $fileIcon.attr('title', tooltip);

        this.listenTo(diffReviewableView, 'chunkDimmed chunkUndimmed',
                      function(chunkID) {
            this.$('a[href="#' + chunkID + '"]').toggleClass('dimmed');
        });
    },

    /*
     * Handler for when an anchor is clicked.
     *
     * Gets the name of the target and emits anchorClicked.
     */
    _onAnchorClicked: function(e) {
        e.preventDefault();
        var target = $(e.target).find('a')[0];
        this.trigger('anchorClicked', target.href.split('#')[1]);
    }
});
