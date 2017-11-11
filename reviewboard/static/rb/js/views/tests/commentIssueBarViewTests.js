suite('rb/views/CommentIssueBarView', function() {
    var commentIssueManager,
        view,
        $dropButton,
        $reopenButton,
        $fixedButton,
        $verifyFixedButton,
        $verifyDroppedButton;

    beforeEach(function() {
        commentIssueManager = new RB.CommentIssueManager({
            reviewRequest: new RB.ReviewRequest()
        });
        view = new RB.CommentIssueBarView({
            commentIssueManager: commentIssueManager,
            issueStatus: 'open',
            reviewID: 1,
            commentID: 2,
            commentType: 'diff_comments',
            interactive: true,
            canVerify: true
        });
        view.render().$el.appendTo($testsScratch);

        $dropButton = view._$buttons.filter('.drop');
        $reopenButton = view._$buttons.filter('.reopen');
        $fixedButton = view._$buttons.filter('.resolve');
        $verifyFixedButton = view._$buttons.filter('.verify-resolved');
        $verifyDroppedButton = view._$buttons.filter('.verify-dropped');
    });

    describe('Actions', function() {
        var comment;

        beforeEach(function() {
            spyOn(commentIssueManager, 'setCommentState');
            expect(view._$buttons.prop('disabled')).toBe(false);

            comment = commentIssueManager.getComment(1, 2, 'diff_comments');
            spyOn(comment, 'ready')
                .and.callFake(function(options) {
                    if (_.isFunction(options.ready)) {
                        options.ready.call(comment);
                    }
                });
        });

        it('Resolving as fixed', function() {
            $fixedButton.click();

            expect(view._$buttons.prop('disabled')).toBe(true);

            expect(commentIssueManager.setCommentState)
                .toHaveBeenCalledWith(1, 2, 'diff_comments', 'resolved');
        });

        it('Dropping', function() {
            $dropButton.click();

            expect(view._$buttons.prop('disabled')).toBe(true);

            expect(commentIssueManager.setCommentState)
                .toHaveBeenCalledWith(1, 2, 'diff_comments', 'dropped');
        });

        it('Re-opening', function() {
            view._showStatus(RB.BaseComment.STATE_RESOLVED);

            $reopenButton.click();

            expect(view._$buttons.prop('disabled')).toBe(true);

            expect(commentIssueManager.setCommentState)
                .toHaveBeenCalledWith(1, 2, 'diff_comments', 'open');
        });

        it('Resolving with verification', function() {
            comment.get('extraData').require_verification = true;

            $fixedButton.click();

            expect(view._$buttons.prop('disabled')).toBe(true);

            expect(commentIssueManager.setCommentState)
                .toHaveBeenCalledWith(1, 2, 'diff_comments',
                                      'verifying-resolved');
         });

        it('Dropping with verification', function() {
            comment.get('extraData').require_verification = true;

            $dropButton.click();

            expect(view._$buttons.prop('disabled')).toBe(true);

            expect(commentIssueManager.setCommentState)
                .toHaveBeenCalledWith(1, 2, 'diff_comments',
                                      'verifying-dropped');
         });
    });

    describe('Event handling', function() {
        describe('CommentIssueManager.issueStatusUpdated', function() {
            beforeEach(function() {
                spyOn(view, '_showStatus');
            });

            it('When comment updated', function() {
                var comment = new RB.DiffComment({
                    id: 2,
                    issueStatus: 'resolved'
                });

                commentIssueManager.trigger('issueStatusUpdated', comment);

                expect(view._showStatus).toHaveBeenCalledWith('resolved');
            });

            it('When different comment updated', function() {
                var comment = new RB.DiffComment({
                    id: 10,
                    issueStatus: 'resolved'
                });

                commentIssueManager.trigger('issueStatusUpdated', comment);

                expect(view._showStatus).not.toHaveBeenCalled();
            });
        });
    });

    describe('Issue states', function() {
        describe('Open', function() {
            beforeEach(function() {
                view._showStatus(RB.BaseComment.STATE_OPEN);
            });

            it('CSS class', function() {
                expect(view._$state.hasClass('open')).toBe(true);
                expect(view._$state.hasClass('resolved')).toBe(false);
                expect(view._$state.hasClass('dropped')).toBe(false);
                expect(view._$state.hasClass('verifying-resolved')).toBe(false);
                expect(view._$state.hasClass('verifying-dropped')).toBe(false);
            });

            it('Text', function() {
                expect(view._$message.text()).toBe('An issue was opened.');
            });

            describe('Button visibility', function() {
                it('"Drop" shown', function() {
                    expect($dropButton.is(':visible')).toBe(true);
                });

                it('"Fixed" shown', function() {
                    expect($fixedButton.is(':visible')).toBe(true);
                });

                it('"Re-open" hidden', function() {
                    expect($reopenButton.is(':visible')).toBe(false);
                });

                it('"Verify Fixed" hidden', function() {
                    expect($verifyFixedButton.is(':visible')).toBe(false);
                });

                it('"Verify Dropped" hidden', function() {
                    expect($verifyDroppedButton.is(':visible')).toBe(false);
                });
            });
        });

        describe('Fixed', function() {
            beforeEach(function() {
                view._showStatus(RB.BaseComment.STATE_RESOLVED);
            });

            it('CSS class', function() {
                expect(view._$state.hasClass('open')).toBe(false);
                expect(view._$state.hasClass('resolved')).toBe(true);
                expect(view._$state.hasClass('dropped')).toBe(false);
                expect(view._$state.hasClass('verifying-resolved')).toBe(false);
                expect(view._$state.hasClass('verifying-dropped')).toBe(false);
            });

            it('Text', function() {
                expect(view._$message.text()).toBe(
                    'The issue has been resolved.');
            });

            describe('Button visibility', function() {
                it('"Drop" hidden', function() {
                    expect($dropButton.is(':visible')).toBe(false);
                });

                it('"Fixed" hidden', function() {
                    expect($fixedButton.is(':visible')).toBe(false);
                });

                it('"Re-open" shown', function() {
                    expect($reopenButton.is(':visible')).toBe(true);
                });

                it('"Verify Fixed" hidden', function() {
                    expect($verifyFixedButton.is(':visible')).toBe(false);
                });

                it('"Verify Dropped" hidden', function() {
                    expect($verifyDroppedButton.is(':visible')).toBe(false);
                });
            });
        });

        describe('Dropped', function() {
            beforeEach(function() {
                view._showStatus(RB.BaseComment.STATE_DROPPED);
            });

            it('CSS class', function() {
                expect(view._$state.hasClass('open')).toBe(false);
                expect(view._$state.hasClass('resolved')).toBe(false);
                expect(view._$state.hasClass('dropped')).toBe(true);
                expect(view._$state.hasClass('verifying-resolved')).toBe(false);
                expect(view._$state.hasClass('verifying-dropped')).toBe(false);
            });

            it('Text', function() {
                expect(view._$message.text()).toBe(
                    'The issue has been dropped.');
            });

            describe('Button visibility', function() {
                it('"Drop" hidden', function() {
                    expect($dropButton.is(':visible')).toBe(false);
                });

                it('"Fixed" hidden', function() {
                    expect($fixedButton.is(':visible')).toBe(false);
                });

                it('"Re-open" shown', function() {
                    expect($reopenButton.is(':visible')).toBe(true);
                });

                it('"Verify Fixed" hidden', function() {
                    expect($verifyFixedButton.is(':visible')).toBe(false);
                });

                it('"Verify Dropped" hidden', function() {
                    expect($verifyDroppedButton.is(':visible')).toBe(false);
                });
            });
        });

        describe('Verifying Fixed', function() {
            beforeEach(function() {
                view._showStatus(RB.BaseComment.STATE_VERIFYING_RESOLVED);
            });

            it('CSS class', function() {
                expect(view._$state.hasClass('open')).toBe(false);
                expect(view._$state.hasClass('resolved')).toBe(false);
                expect(view._$state.hasClass('dropped')).toBe(false);
                expect(view._$state.hasClass('verifying-resolved')).toBe(true);
                expect(view._$state.hasClass('verifying-dropped')).toBe(false);
            });

            it('Text', function() {
                expect(view._$message.text()).toBe(
                    'Waiting for verification before resolving...');
            });

            describe('Button visibility', function() {
                it('"Drop" hidden', function() {
                    expect($dropButton.is(':visible')).toBe(false);
                });

                it('"Fixed" hidden', function() {
                    expect($fixedButton.is(':visible')).toBe(false);
                });

                it('"Re-open" shown', function() {
                    expect($reopenButton.is(':visible')).toBe(true);
                });

                it('"Verify Fixed" shown', function() {
                    expect($verifyFixedButton.is(':visible')).toBe(true);
                });

                it('"Verify Dropped" hidden', function() {
                    expect($verifyDroppedButton.is(':visible')).toBe(false);
                });
            });
        });

        describe('Verifying Dropped', function() {
            beforeEach(function() {
                view._showStatus(RB.BaseComment.STATE_VERIFYING_DROPPED);
            });

            it('CSS class', function() {
                expect(view._$state.hasClass('open')).toBe(false);
                expect(view._$state.hasClass('resolved')).toBe(false);
                expect(view._$state.hasClass('dropped')).toBe(false);
                expect(view._$state.hasClass('verifying-resolved')).toBe(false);
                expect(view._$state.hasClass('verifying-dropped')).toBe(true);
            });

            it('Text', function() {
                expect(view._$message.text()).toBe(
                    'Waiting for verification before dropping...');
            });

            describe('Button visibility', function() {
                it('"Drop" hidden', function() {
                    expect($dropButton.is(':visible')).toBe(false);
                });

                it('"Fixed" hidden', function() {
                    expect($fixedButton.is(':visible')).toBe(false);
                });

                it('"Re-open" shown', function() {
                    expect($reopenButton.is(':visible')).toBe(true);
                });

                it('"Verify Fixed" hidden', function() {
                    expect($verifyFixedButton.is(':visible')).toBe(false);
                });

                it('"Verify Dropped" shown', function() {
                    expect($verifyDroppedButton.is(':visible')).toBe(true);
                });
            });
        });
    });
});
