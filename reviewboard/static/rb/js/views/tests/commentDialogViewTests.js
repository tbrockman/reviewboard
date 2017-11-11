suite('rb/views/CommentDialogView', function() {
    var reviewRequestEditor,
        reviewRequest;

    beforeEach(function() {
        RB.DnDUploader.create();

        reviewRequest = new RB.ReviewRequest();
        reviewRequestEditor = new RB.ReviewRequestEditor({
            reviewRequest: reviewRequest
        });
    });

    afterEach(function() {
        RB.DnDUploader.instance = null;
    });

    describe('Class methods', function() {
        describe('create', function() {
            it('Without a comment', function() {
                expect(function() {
                    RB.CommentDialogView.create({
                        animate: false,
                        container: $testsScratch,
                        reviewRequestEditor: reviewRequestEditor
                    });
                }).toThrow();

                expect(RB.CommentDialogView._instance).toBeFalsy();
                expect($testsScratch.children().length).toBe(0);
            });

            it('With a comment', function() {
                var dlg = RB.CommentDialogView.create({
                    animate: false,
                    comment: new RB.DiffComment(),
                    container: $testsScratch,
                    reviewRequestEditor: reviewRequestEditor
                });

                expect(dlg).toBeTruthy();
                expect(RB.CommentDialogView._instance).toBe(dlg);
                expect($testsScratch.children().length).toBe(1);
            });

            it('Replacing an open dialog', function() {
                var dlg1,
                    dlg2;

                dlg1 = RB.CommentDialogView.create({
                    animate: false,
                    comment: new RB.DiffComment(),
                    container: $testsScratch,
                    reviewRequestEditor: reviewRequestEditor
                });
                expect(dlg1).toBeTruthy();

                dlg2 = RB.CommentDialogView.create({
                    animate: false,
                    comment: new RB.DiffComment(),
                    container: $testsScratch,
                    reviewRequestEditor: reviewRequestEditor
                });
                expect(dlg2).toBeTruthy();

                expect(dlg2).not.toBe(dlg1);
                expect(dlg1.$el.parents().length).toBe(0);
                expect(RB.CommentDialogView._instance).toBe(dlg2);
                expect($testsScratch.children().length).toBe(1);
            });
        });
    });

    describe('Instances', function() {
        var editor,
            dlg;

        beforeEach(function() {
            editor = new RB.CommentEditor({
                comment: new RB.DiffComment(),
                canEdit: true,
                reviewRequest: reviewRequest,
                reviewRequestEditor: reviewRequestEditor
            });

            dlg = new RB.CommentDialogView({
                animate: false,
                model: editor,
                commentIssueManager: new RB.CommentIssueManager()
            });

            dlg.on('closed', function() {
                dlg = null;
            });

            dlg.render().$el.appendTo($testsScratch);
        });

        afterEach(function() {
            if (dlg) {
                dlg.close();
            }
        });

        describe('Buttons', function() {
            beforeEach(function() {
                dlg.open();
            });

            describe('Cancel', function() {
                var $button;

                beforeEach(function() {
                    $button = dlg.$el.find('.buttons .cancel');
                });

                it('Enabled', function() {
                    expect($button.is(':disabled')).toBe(false);
                });

                it('Cancels editor when clicked', function() {
                    spyOn(editor, 'cancel');
                    $button.click();
                    expect(editor.cancel).toHaveBeenCalled();
                });

                it('Closes dialog when clicked', function() {
                    spyOn(editor, 'cancel');
                    spyOn(dlg, 'close');
                    $button.click();
                    expect(dlg.close).toHaveBeenCalled();
                });

                it('Confirms before cancelling unsaved comment', function() {
                    spyOn(editor, 'cancel');
                    spyOn(dlg, 'close');
                    spyOn(window, 'confirm').and.returnValue(true);
                    editor.set('dirty', true);
                    $button.click();
                    expect(dlg.close).toHaveBeenCalled();
                });

                it('Cancel close when unsaved comment', function() {
                    spyOn(editor, 'cancel');
                    spyOn(dlg, 'close');
                    spyOn(window, 'confirm').and.returnValue(false);
                    editor.set('dirty', true);
                    $button.click();
                    expect(dlg.close).not.toHaveBeenCalled();
                });

                describe('Visibility', function() {
                    it('Shown when canEdit=true', function() {
                        editor.set('canEdit', true);
                        expect($button.is(':visible')).toBe(true);
                    });

                    it('Hidden when canEdit=false', function() {
                        editor.set('canEdit', false);
                        expect($button.is(':visible')).toBe(false);
                    });
                });
            });

            describe('Close', function() {
                var $button;

                beforeEach(function() {
                    $button = dlg.$el.find('.buttons .close');
                });

                it('Cancels editor when clicked', function() {
                    spyOn(editor, 'cancel');
                    $button.click();
                    expect(editor.cancel).toHaveBeenCalled();
                });

                it('Closes dialog when clicked', function() {
                    spyOn(editor, 'cancel');
                    spyOn(dlg, 'close');
                    $button.click();
                    expect(dlg.close).toHaveBeenCalled();
                });

                describe('Visibility', function() {
                    it('Shown when canEdit=false', function() {
                        editor.set('canEdit', false);
                        expect($button.is(':visible')).toBe(true);
                    });

                    it('Hidden when canEdit=true', function() {
                        editor.set('canEdit', true);
                        expect($button.is(':visible')).toBe(false);
                    });
                });
            });

            describe('Delete', function() {
                var $button;

                beforeEach(function() {
                    $button = dlg.$el.find('.buttons .delete');
                });

                it('Cancels editor when clicked', function() {
                    editor.set('canDelete', true);
                    spyOn(editor, 'deleteComment');
                    $button.click();
                    expect(editor.deleteComment).toHaveBeenCalled();
                });

                it('Closes dialog when clicked', function() {
                    editor.set('canDelete', true);
                    spyOn(editor, 'deleteComment');
                    spyOn(dlg, 'close');
                    $button.click();
                    expect(dlg.close).toHaveBeenCalled();
                });

                describe('Enabled state', function() {
                    it('Enabled when editor.canDelete=true', function() {
                        editor.set('canDelete', true);
                        expect($button.is(':disabled')).toBe(false);
                    });

                    it('Disabled when editor.canDelete=false', function() {
                        editor.set('canDelete', false);
                        expect($button.is(':disabled')).toBe(true);
                    });
                });

                describe('Visibility', function() {
                    it('Shown when canDelete=true', function() {
                        editor.set('canDelete', true);
                        expect($button.is(':visible')).toBe(true);
                    });

                    it('Hidden when caDelete=false', function() {
                        editor.set('canDelete', false);
                        expect($button.is(':visible')).toBe(false);
                    });
                });
            });

            describe('Save', function() {
                var $button;

                beforeEach(function() {
                    $button = dlg.$el.find('.buttons .save');
                });

                it('Cancels editor when clicked', function() {
                    editor.set('canSave', true);
                    spyOn(editor, 'save');
                    $button.click();
                    expect(editor.save).toHaveBeenCalled();
                });

                it('Closes dialog when clicked', function() {
                    editor.set('canSave', true);
                    spyOn(editor, 'save');
                    spyOn(dlg, 'close');
                    $button.click();
                    expect(dlg.close).toHaveBeenCalled();
                });

                describe('Enabled state', function() {
                    it('Enabled when editor.canSave=true', function() {
                        editor.set('canSave', true);
                        expect($button.is(':disabled')).toBe(false);
                    });

                    it('Disabled when editor.canSave=false', function() {
                        editor.set('canSave', false);
                        expect($button.is(':disabled')).toBe(true);
                    });
                });

                describe('Visibility', function() {
                    it('Shown when canEdit=true', function() {
                        editor.set('canEdit', true);
                        expect($button.is(':visible')).toBe(true);
                    });

                    it('Hidden when canEdit=false', function() {
                        editor.set('canEdit', false);
                        expect($button.is(':visible')).toBe(false);
                    });
                });
            });
        });

        describe('Fields', function() {
            beforeEach(function() {
                dlg.open();
            });

            describe('Open an Issue checkbox', function() {
                describe('Visibility', function() {
                    it('Shown when canEdit=true', function() {
                        editor.set('canEdit', true);
                        expect(dlg._$issueOptions.is(':visible')).toBe(true);
                    });

                    it('Hidden when canEdit=false', function() {
                        editor.set('canEdit', false);
                        expect(dlg._$issueOptions.is(':visible')).toBe(false);
                    });
                });
            });

            describe('Textbox', function() {
                describe('Visibility', function() {
                    it('Shown when canEdit=true', function() {
                        editor.set('canEdit', true);
                        expect(dlg._textEditor.$el.is(':visible')).toBe(true);
                    });

                    it('Hidden when canEdit=false', function() {
                        editor.set('canEdit', false);
                        expect(dlg._textEditor.$el.is(':visible')).toBe(false);
                    });
                });
            });
        });

        describe('Height', function() {
            beforeEach(function() {
                editor = new RB.CommentEditor({
                    comment: new RB.DiffComment(),
                    reviewRequest: reviewRequest,
                    reviewRequestEditor: reviewRequestEditor
                });

                dlg = new RB.CommentDialogView({
                    animate: false,
                    model: editor
                });
            });

            it('When canEdit=true', function() {
                editor.set('canEdit', true);
                dlg.render();
                dlg.open();
                expect(dlg.$el.height()).toBe(
                    RB.CommentDialogView.prototype.DIALOG_TOTAL_HEIGHT);
            });

            it('When canEdit=false', function() {
                editor.set('canEdit', false);
                dlg.render();
                dlg.open();
                expect(dlg.$el.height()).toBe(
                    RB.CommentDialogView.prototype.DIALOG_NON_EDITABLE_HEIGHT);
            });
        });

        describe('Other published comments list', function() {
            var $commentsList,
                $commentsPane;

            beforeEach(function() {
                $commentsPane = dlg.$el.find('.other-comments');
                $commentsList = $commentsPane.children('ul');
                expect($commentsList.length).toBe(1);
            });

            describe('Empty list', function() {
                it('Hidden pane', function() {
                    expect($commentsPane.is(':visible')).toBe(false);
                });
            });

            describe('Populated list', function() {
                var comment,
                    commentReply,
                    parentCommentReplyLink;

                beforeEach(function() {
                    comment = new RB.DiffComment();
                    comment.user = {
                        'name': 'Test User'
                    };
                    comment.url = 'http://example.com/';
                    comment.comment_id = 1;
                    comment.text = 'Sample comment.';
                    comment.issue_opened = false;
                    parentCommentReplyLink = '/?reply_id=' + comment.comment_id;

                    commentReply = new RB.DiffComment();
                    commentReply.user = {
                        'name': 'Test User'
                    };
                    commentReply.url = 'http://example.com/';
                    commentReply.comment_id = 2;
                    commentReply.text = 'Sample comment.';
                    commentReply.issue_opened = false;
                    commentReply.reply_to_id = 1;
                });

                describe('Visible pane', function() {
                    it('Setting list before opening dialog', function() {
                        editor.set('publishedComments', [comment]);
                        dlg.open();
                        expect($commentsPane.is(':visible')).toBe(true);
                    });

                    it('Setting list after opening dialog', function() {
                        dlg.open();
                        editor.set('publishedComments', [comment]);
                        expect($commentsPane.is(':visible')).toBe(true);
                    });
                });

                it('List items added', function() {
                    dlg.open();
                    editor.set('publishedComments', [comment]);
                    expect($commentsList.children().length).toBe(1);
                });

                it('Parent comment reply link links to itself', function(){
                    var $replyLink;
                    editor.set('publishedComments', [comment]);
                    dlg.open();
                    $replyLink = $commentsList.find('.comment-list-reply-action');
                    expect($replyLink[0].href).toContain(parentCommentReplyLink);
                });

                it('Both parent and reply comment reply links link to parent comment', function(){
                    var $replyLinks;
                    editor.set('publishedComments', [comment, commentReply]);
                    dlg.open();
                    $replyLinks = $commentsList.find('.comment-list-reply-action');
                    expect($replyLinks.length).toEqual(2);
                    expect($replyLinks[0].href).toContain(parentCommentReplyLink);
                    expect($replyLinks[1].href).toContain(parentCommentReplyLink);
                });
            });

            describe('Issue bar buttons', function() {
                var comment;

                beforeEach(function() {
                    comment = new RB.DiffComment();
                    comment.user = {
                        'name': 'Test User'
                    };
                    comment.url = 'http://example.com/';
                    comment.comment_id = 1;
                    comment.text = 'Sample comment.';
                    comment.issue_opened = true;
                    comment.issue_status = 'open';
                });

                it('When interactive', function() {
                    var $buttons;

                    reviewRequestEditor.set('editable', true);
                    editor.set('publishedComments', [comment]);

                    dlg = new RB.CommentDialogView({
                        animate: false,
                        model: editor,
                        commentIssueManager: new RB.CommentIssueManager()
                    });
                    dlg.render().$el.appendTo($testsScratch);
                    dlg.open();

                    $buttons = dlg.$el.find('.other-comments .issue-button');
                    expect($buttons.length).toBe(5);
                    expect($buttons.is(':visible')).toBe(true);
                });

                it('When not interactive', function() {
                    var $buttons;

                    reviewRequestEditor.set('editable', false);
                    editor.set('publishedComments', [comment]);

                    dlg = new RB.CommentDialogView({
                        animate: false,
                        model: editor,
                        commentIssueManager: new RB.CommentIssueManager()
                    });
                    dlg.render().$el.appendTo($testsScratch);
                    dlg.open();

                    $buttons = dlg.$el.find('.other-comments .issue-button');
                    expect($buttons.length).toBe(0);
                });
            });
        });

        describe('Methods', function() {
            describe('close', function() {
                it('Editor state', function() {
                    dlg.open();
                    expect(editor.get('editing')).toBe(true);
                    dlg.close();
                    expect(editor.get('editing')).toBe(false);
                });

                it('Dialog removed', function() {
                    dlg.open();

                    spyOn(dlg, 'trigger');

                    dlg.close();
                    expect(dlg.trigger).toHaveBeenCalledWith('closed');
                    expect(dlg.$el.parents().length).toBe(0);
                    expect($testsScratch.children().length).toBe(0);
                });
            });

            describe('open', function() {
                it('Editor state', function() {
                    expect(editor.get('editing')).toBe(false);
                    dlg.open();
                    expect(editor.get('editing')).toBe(true);
                });

                it('Visibility', function() {
                    expect(dlg.$el.is(':visible')).toBe(false);
                    dlg.open();
                    expect(dlg.$el.is(':visible')).toBe(true);
                });

                it('Default focus', function() {
                    var $textarea = dlg.$el.find('textarea');

                    expect($textarea.is(':focus')).toBe(false);
                    spyOn($textarea[0], 'focus');

                    dlg.open();
                    expect($textarea[0].focus).toHaveBeenCalled();
                });
            });
        });

        describe('Special keys', function() {
            var $textarea;

            function simulateKeyPress(c, altKey, ctrlKey, metaKey) {
                var e;

                $textarea.focus();

                _.each(['keydown', 'keypress', 'keyup'], function(type) {
                    e = $.Event(type);
                    e.which = c;
                    e.altKey = altKey;
                    e.ctrlKey = ctrlKey;
                    e.metaKey = metaKey;
                    $textarea.trigger(e);
                });
            }

            function setupForRichText(richText, canSave) {
                editor.set('richText', richText);
                editor.set('canSave', !!canSave);
                $textarea = dlg.$('textarea');
            }

            beforeEach(function() {
                dlg.open();
                $textarea = dlg.$('textarea');
            });

            describe('Control-Enter to save', function() {
                beforeEach(function() {
                    spyOn(editor, 'save');
                    spyOn(dlg, 'close');
                });

                describe('With editor.canSave=true', function() {
                    describe('Keycode 10', function() {
                        it('If Markdown', function() {
                            setupForRichText(true, true);

                            simulateKeyPress(10, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false, true);

                            simulateKeyPress(10, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });
                    });

                    describe('Keycode 13', function() {
                        it('If Markdown', function() {
                            setupForRichText(true, true);

                            simulateKeyPress(13, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false, true);

                            simulateKeyPress(13, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });
                    });
                });

                describe('With editor.canSave=false', function() {
                    beforeEach(function() {
                        editor.set('canSave', false);
                    });

                    describe('Keycode 10', function() {
                        it('If Markdown', function() {
                            setupForRichText(true);

                            simulateKeyPress(10, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false);

                            simulateKeyPress(10, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });
                    });

                    describe('Keycode 13', function() {
                        it('If Markdown', function() {
                            setupForRichText(true);

                            simulateKeyPress(13, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false);

                            simulateKeyPress(13, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });
                    });
                });
            });

            describe('Command-Enter to save', function() {
                beforeEach(function() {
                    spyOn(editor, 'save');
                    spyOn(dlg, 'close');
                });

                describe('With editor.canSave=true', function() {
                    describe('Keycode 10', function() {
                        it('If Markdown', function() {
                            setupForRichText(true, true);

                            simulateKeyPress(10, false, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false, true);

                            simulateKeyPress(10, false, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });
                    });

                    describe('Keycode 13', function() {
                        it('If Markdown', function() {
                            setupForRichText(true, true);

                            simulateKeyPress(13, false, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false, true);

                            simulateKeyPress(13, false, false, true);
                            expect(editor.save).toHaveBeenCalled();
                            expect(dlg.close).toHaveBeenCalled();
                        });
                    });
                });

                describe('With editor.canSave=false', function() {
                    beforeEach(function() {
                        editor.set('canSave', false);
                    });

                    describe('Keycode 10', function() {
                        it('If Markdown', function() {
                            setupForRichText(true);

                            simulateKeyPress(10, false, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false);

                            simulateKeyPress(10, false, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });
                    });

                    describe('Keycode 13', function() {
                        it('If Markdown', function() {
                            setupForRichText(true);

                            simulateKeyPress(13, false, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });

                        it('If plain text', function() {
                            setupForRichText(false);

                            simulateKeyPress(13, false, false, true);
                            expect(editor.save).not.toHaveBeenCalled();
                            expect(dlg.close).not.toHaveBeenCalled();
                        });
                    });
                });
            });

            describe('Escape to cancel', function() {
                describe('Pressing escape in text area', function() {
                    beforeEach(function() {
                        spyOn(editor, 'cancel');
                        spyOn(dlg, 'close');
                    });

                    it('If Markdown', function() {
                        spyOn(window, 'confirm').and.returnValue(true);
                        setupForRichText(true);

                        simulateKeyPress($.ui.keyCode.ESCAPE, false, false);
                        expect(editor.cancel).toHaveBeenCalled();
                        expect(window.confirm).toHaveBeenCalled();
                        expect(dlg.close).toHaveBeenCalled();
                    });

                    it('If plain text', function() {
                        setupForRichText(false);

                        simulateKeyPress($.ui.keyCode.ESCAPE, false, false);
                        expect(editor.cancel).toHaveBeenCalled();
                        expect(dlg.close).toHaveBeenCalled();
                    });

                    it('If unsaved comment', function() {
                        spyOn(window, 'confirm').and.returnValue(true);
                        editor.set('dirty', true);

                        simulateKeyPress($.ui.keyCode.ESCAPE, false, false);
                        expect(editor.cancel).toHaveBeenCalled();
                        expect(window.confirm).toHaveBeenCalled();
                        expect(dlg.close).toHaveBeenCalled();
                    });

                    it('If unsaved comment, do not close', function() {
                        spyOn(window, 'confirm').and.returnValue(false);
                        editor.set('dirty', true);

                        simulateKeyPress($.ui.keyCode.ESCAPE, false, false);
                        expect(editor.cancel).not.toHaveBeenCalled();
                        expect(window.confirm).toHaveBeenCalled();
                        expect(dlg.close).not.toHaveBeenCalled();
                    });
                });
            });

            describe('Toggle open issue', function() {
                var $checkbox;

                function runToggleIssueTest(richText, startState, keyCode) {
                    setupForRichText(richText);
                    $checkbox.prop('checked', startState);
                    editor.set('openIssue', startState);

                    simulateKeyPress(keyCode.charCodeAt(0), true, false);

                    expect($checkbox.prop('checked')).toBe(!startState);
                    expect(editor.get('openIssue')).toBe(!startState);
                    expect($textarea.val()).toBe('');
                }

                beforeEach(function() {
                    $checkbox = dlg.$el.find('input[type=checkbox]');
                });

                describe('Alt-I', function() {
                    describe('Checked to unchecked', function() {
                        it('If Markdown', function() {
                            runToggleIssueTest(true, true, 'I');
                        });

                        it('If Markdown', function() {
                            runToggleIssueTest(false, true, 'I');
                        });
                    });

                    describe('Unchecked to checked', function() {
                        it('If Markdown', function() {
                            runToggleIssueTest(true, false, 'I');
                        });

                        it('If plain text', function() {
                            runToggleIssueTest(false, false, 'I');
                        });
                    });
                });

                describe('Alt-i', function() {
                    describe('Checked to unchecked', function() {
                        it('If Markdown', function() {
                            runToggleIssueTest(true, true, 'i');
                        });

                        it('If plain text', function() {
                            runToggleIssueTest(false, true, 'i');
                        });
                    });

                    describe('Unchecked to checked', function() {
                        it('If Markdown', function() {
                            runToggleIssueTest(true, false, 'i');
                        });

                        it('If plain text', function() {
                            runToggleIssueTest(false, false, 'i');
                        });
                    });
                });
            });
        });

        describe('Title text', function() {
            var $title;

            beforeEach(function() {
                dlg.open();
                $title = dlg.$el.find('form .title');
            });

            it('Default state', function() {
                expect($title.text()).toBe('Your comment');
            });

            it('Setting dirty=true', function() {
                editor.set('dirty', true);
                expect($title.text()).toBe('Your comment (unsaved)');
            });

            it('Setting dirty=false', function() {
                editor.set('dirty', true);
                editor.set('dirty', false);

                expect($title.text()).toBe('Your comment');
            });
        });

        describe('State synchronization', function() {
            describe('Comment text', function() {
                var $textarea;

                beforeEach(function() {
                    dlg.open();
                    $textarea = $(dlg._textEditor.$('textarea'));
                });

                describe('Dialog to editor', function() {
                    var text = 'foo';

                    beforeEach(function(done) {
                        var i,
                            c,
                            e,
                            t;

                        dlg._textEditor.on('change', function() {
                            changed = true;
                        });

                        $textarea.focus();

                        for (i = 0; i < text.length; i++) {
                            c = text.charCodeAt(i);

                            e = $.Event('keydown');
                            e.which = c;
                            $textarea.trigger(e);

                            e = $.Event('keypress');
                            e.which = c;
                            $textarea.trigger(e);

                            dlg._textEditor.setText(dlg._textEditor.getText() +
                                                    text[i]);

                            e = $.Event('keyup');
                            e.which = c;
                            $textarea.trigger(e);
                        }

                        t = setInterval(function() {
                            if (dlg._textEditor.getText() === text) {
                                clearInterval(t);
                                done();
                            }
                        }, 100);
                    });

                    it('', function() {
                        expect(editor.get('text')).toEqual(text);
                    });
                });

                it('Editor to dialog', function() {
                    var text = 'bar';

                    editor.set('text', text);
                    expect(dlg._textEditor.getText()).toEqual(text);
                });
            });

            describe('Open Issue checkbox', function() {
                var $checkbox;

                beforeEach(function() {
                    dlg.open();
                    $checkbox = dlg.$('#comment_issue');
                    $checkbox.prop('checked', false);
                    editor.set('openIssue', false);
                });

                it('Dialog to editor', function() {
                    $checkbox.click();
                    expect(editor.get('openIssue')).toBe(true);
                });

                it('Editor to dialog', function() {
                    editor.set('openIssue', true);
                    expect($checkbox.prop('checked')).toBe(true);
                });
            });

            describe('Enable Markdown checkbox', function() {
                var $checkbox;

                beforeEach(function() {
                    dlg.open();
                    $checkbox = dlg.$('#enable_markdown');
                    $checkbox.prop('checked', false);
                    editor.set('richText', false);
                    expect(dlg._textEditor.richText).toBe(false);
                });

                it('Dialog to editor', function() {
                    $checkbox.click();
                    expect(editor.get('richText')).toBe(true);
                    expect(dlg._textEditor.richText).toBe(true);
                });

                it('Editor to dialog', function() {
                    editor.set('richText', true);
                    expect($checkbox.prop('checked')).toBe(true);
                    expect(dlg._textEditor.richText).toBe(true);
                });
            });
        });

        describe('User preference defaults', function() {
            describe('Open Issue checkbox', function() {
                it('When commentsOpenAnIssue is true', function() {
                    RB.UserSession.instance.set('commentsOpenAnIssue', true);

                    editor = new RB.CommentEditor({
                        reviewRequest: reviewRequest,
                        reviewRequestEditor: reviewRequestEditor
                    });
                    dlg = new RB.CommentDialogView({
                        animate: false,
                        model: editor
                    });
                    dlg.render();
                    $checkbox = dlg.$('#comment_issue');

                    expect(editor.get('openIssue')).toBe(true);
                    expect($checkbox.prop('checked')).toBe(true);
                });

                it('When commentsOpenAnIssue is false', function() {
                    RB.UserSession.instance.set('commentsOpenAnIssue', false);

                    editor = new RB.CommentEditor({
                        reviewRequest: reviewRequest,
                        reviewRequestEditor: reviewRequestEditor
                    });
                    dlg = new RB.CommentDialogView({
                        animate: false,
                        model: editor
                    });
                    dlg.render();
                    $checkbox = dlg.$('#comment_issue');

                    expect(editor.get('openIssue')).toBe(false);
                    expect($checkbox.prop('checked')).toBe(false);
                });
            });

            describe('Enable Markdown checkbox', function() {
                describe('When defaultUseRichText is true', function() {
                    beforeEach(function() {
                        RB.UserSession.instance.set('defaultUseRichText', true);
                    });

                    it('New comment', function() {
                        editor = new RB.CommentEditor({
                            reviewRequest: reviewRequest,
                            reviewRequestEditor: reviewRequestEditor
                        });
                        dlg = new RB.CommentDialogView({
                            animate: false,
                            model: editor
                        });
                        dlg.render();
                        $checkbox = dlg.$('#enable_markdown');

                        expect(editor.get('richText')).toBe(true);
                        expect($checkbox.prop('checked')).toBe(true);
                        expect(dlg._textEditor.richText).toBe(true);
                    });

                    it('Existing comment with richText=true', function() {
                        editor = new RB.CommentEditor({
                            reviewRequest: reviewRequest,
                            reviewRequestEditor: reviewRequestEditor,
                            comment: new RB.DiffComment({
                                richText: true
                            })
                        });
                        dlg = new RB.CommentDialogView({
                            animate: false,
                            model: editor
                        });
                        dlg.render();
                        $checkbox = dlg.$('#enable_markdown');

                        expect(editor.get('richText')).toBe(true);
                        expect($checkbox.prop('checked')).toBe(true);
                        expect(dlg._textEditor.richText).toBe(true);
                    });

                    it('Existing comment with richText=false', function() {
                        editor = new RB.CommentEditor({
                            reviewRequest: reviewRequest,
                            reviewRequestEditor: reviewRequestEditor,
                            comment: new RB.DiffComment({
                                richText: false
                            })
                        });
                        dlg = new RB.CommentDialogView({
                            animate: false,
                            model: editor
                        });
                        dlg.render();
                        $checkbox = dlg.$('#enable_markdown');

                        expect(editor.get('richText')).toBe(true);
                        expect($checkbox.prop('checked')).toBe(true);
                        expect(dlg._textEditor.richText).toBe(true);
                    });
                });

                describe('When defaultUseRichText is false', function() {
                    beforeEach(function() {
                        RB.UserSession.instance.set('defaultUseRichText',
                                                    false);
                    });

                    it('New comment', function() {
                        editor = new RB.CommentEditor({
                            reviewRequest: reviewRequest,
                            reviewRequestEditor: reviewRequestEditor
                        });
                        dlg = new RB.CommentDialogView({
                            animate: false,
                            model: editor
                        });
                        dlg.render();
                        $checkbox = dlg.$('#enable_markdown');

                        expect(editor.get('richText')).toBe(false);
                        expect($checkbox.prop('checked')).toBe(false);
                        expect(dlg._textEditor.richText).toBe(false);
                    });

                    it('Existing comment with richText=true', function() {
                        editor = new RB.CommentEditor({
                            reviewRequest: reviewRequest,
                            reviewRequestEditor: reviewRequestEditor,
                            comment: new RB.DiffComment({
                                richText: true
                            })
                        });
                        dlg = new RB.CommentDialogView({
                            animate: false,
                            model: editor
                        });
                        dlg.render();
                        $checkbox = dlg.$('#enable_markdown');

                        expect(editor.get('richText')).toBe(true);
                        expect($checkbox.prop('checked')).toBe(true);
                        expect(dlg._textEditor.richText).toBe(true);
                    });

                    it('Existing comment with richText=false', function() {
                        editor = new RB.CommentEditor({
                            reviewRequest: reviewRequest,
                            reviewRequestEditor: reviewRequestEditor,
                            comment: new RB.DiffComment({
                                richText: false
                            })
                        });
                        dlg = new RB.CommentDialogView({
                            animate: false,
                            model: editor
                        });
                        dlg.render();
                        $checkbox = dlg.$('#enable_markdown');

                        expect(editor.get('richText')).toBe(false);
                        expect($checkbox.prop('checked')).toBe(false);
                        expect(dlg._textEditor.richText).toBe(false);
                    });
                });
            });
        });

        describe('Logged Out indicator', function() {
            it('When logged in', function() {
                RB.UserSession.instance.set('authenticated', true);

                dlg = new RB.CommentDialogView({
                    animate: false,
                    model: new RB.CommentEditor({
                        reviewRequest: reviewRequest,
                        reviewRequestEditor: reviewRequestEditor
                    })
                });
                dlg.render();

                expect(dlg.$el.find('p[class="login-text"]').length).toBe(0);
            });

            it('When logged out', function() {
                RB.UserSession.instance.set('authenticated', false);

                dlg = new RB.CommentDialogView({
                    animate: false,
                    model: new RB.CommentEditor({
                        reviewRequest: reviewRequest,
                        reviewRequestEditor: reviewRequestEditor
                    })
                });
                dlg.render();

                expect(dlg.$el.find('p[class="login-text"]').length).toBe(1);
            });
        });

        describe('In Draft indicator', function() {
            it('Shown when hasDraft=true', function() {
                reviewRequest.set('hasDraft', true);

                dlg = new RB.CommentDialogView({
                    animate: false,
                    model: new RB.CommentEditor({
                        reviewRequest: reviewRequest,
                        reviewRequestEditor: reviewRequestEditor
                    })
                });
                dlg.render();

                expect(dlg.$el.find('p[class="draft-warning"]').length)
                    .toBe(1);
            });

            it('Hidden when hasDraft=false', function() {
                reviewRequest.set('hasDraft', false);

                dlg = new RB.CommentDialogView({
                    animate: false,
                    model: new RB.CommentEditor({
                        reviewRequest: reviewRequest,
                        reviewRequestEditor: reviewRequestEditor
                    })
                });
                dlg.render();

                expect(dlg.$el.find('p[class="draft-warning"]').length)
                    .toBe(0);
            });
        });
    });
});
