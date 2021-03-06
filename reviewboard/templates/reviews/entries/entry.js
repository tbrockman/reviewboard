{% load djblets_js %}

page.addEntryView(new {{entry.js_view_class}}({
    {{entry.get_js_view_data|json_dumps_items:','}}
    el: $('#{{entry.get_dom_element_id}}'),
    reviewRequestEditorView: page.reviewRequestEditorView,
    model: new {{entry.js_model_class}}({
        id: '{{entry.entry_id|escapejs}}',
        timestamp: {{entry.timestamp|json_dumps}},
        typeID: '{{entry.entry_type_id|escapejs}}',
        {{entry.get_js_model_data|json_dumps_items:','}}
        reviewRequestEditor: page.model.reviewRequestEditor
    }, {
        parse: true
    })
}));
