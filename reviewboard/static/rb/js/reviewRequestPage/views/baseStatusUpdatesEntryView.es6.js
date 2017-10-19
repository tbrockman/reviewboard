(function() {


const ParentView = RB.ReviewRequestPage.EntryView;


/**
 * Base class for an entry that can contain status updates.
 *
 * This manages the views for each review on the status updates, and watches
 * for updates to the entry so that any completed status updates can be
 * shown without a page reload.
 */
RB.ReviewRequestPage.BaseStatusUpdatesEntryView = ParentView.extend({
    CHECK_UPDATES_MS: 10 * 1000,  // 10 seconds

    /**
     * Initialize the view.
     */
    initialize() {
        ParentView.prototype.initialize.apply(this, arguments);

        this._reviewViews = null;
    },

    /**
     * Save state before applying an update.
     *
     * This will save all the loaded diff fragments on the entry so that
     * they'll be loaded from cache when processing the fragments again for
     * the entry after reload.
     */
    beforeApplyUpdate() {
        /*
         * Stop watching for any updates. If there are still status updates
         * pending, render() will re-register for updates.
         */
        this.model.stopWatchingUpdates();

        /*
         * Store any diff fragments for the reload, so we don't have to
         * fetch them again from the server.
         */
        const diffFragmentQueue = RB.PageManager.getPage().diffFragmentQueue;
        const diffCommentsData = this.model.get('diffCommentsData') || [];

        for (let i = 0; i < diffCommentsData.length; i++) {
            diffFragmentQueue.saveFragment(diffCommentsData[i][0]);
        }
    },

    /**
     * Render the entry.
     *
     * This will construct a view for each review associated with a status
     * update.
     *
     * Returns:
     *     RB.ReviewRequestPage.BaseStatusUpdatesEntryView:
     *     This object, for chaining.
     */
    render() {
        ParentView.prototype.render.call(this);

        this._reviewViews = this.model.get('reviews').map(review => {
            const $reviewEl = this.$(`#review${review.id}`);

            const view = new RB.ReviewRequestPage.ReviewView({
                el: $reviewEl,
                model: review,
                entryModel: this.model,
                $bannerFloatContainer: $reviewEl,
                $bannerParent: $reviewEl.children('.banners'),
                bannerNoFloatContainerClass: 'collapsed',
            });
            view.render();

            this.setupReviewView(view);

            return view;
        });

        if (this.model.get('pendingStatusUpdates')) {
            this.model.watchUpdates(this.CHECK_UPDATES_MS);
        }

        return this;
    },

    /**
     * Set up a review view.
     *
     * Subclasses can override this to provide additional setup for review
     * views rendered on the page.
     *
     * Args:
     *     view (RB.ReviewRequestPage.ReviewView):
     *         The review view being set up.
     */
    setupReviewView(view) {
    },
});


})();
