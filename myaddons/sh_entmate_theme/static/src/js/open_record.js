/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ActionMenus } from "@web/search/action_menus/action_menus";

patch(ListRenderer.prototype, {
  /**
   * @override
   */
  setup() {
    this.show_open_record_new_tab_button_listrenderer =
    session.sh_enable_open_record_in_new_tab;
    this.is_list_view = true;
    var Many2one_protect = this["env"]["config"]["actionType"];
    var view_type = this["props"]["activeActions"]["type"];
    if (view_type != "view" || Many2one_protect == false) {
      this.is_list_view = false;
    }
    super.setup();
  },

  /**
   * True when the extra "Open in new tab" column is rendered (see the
   * web.ListRenderer.RecordRow_sh / web.ListRenderer_sh_open_header templates).
   * The column is injected right after the record-selector cell.
   */
  get sh_hasOpenRecordColumn() {
    return this.is_list_view && this.show_open_record_new_tab_button_listrenderer;
  },

  /**
   * Account for the extra column in the total column count so full-width rows
   * (empty state, "load more", group footers) keep the correct colspan.
   * @override
   */
  get nbCols() {
    let nbCols = super.nbCols;
    if (this.sh_hasOpenRecordColumn) {
      nbCols++;
    }
    return nbCols;
  },

  /**
   * The group-name cell spans every column up to the first aggregate (this is
   * also used for the list footer). Our extra column sits before the field
   * columns, so widen that span by one to keep aggregates aligned.
   * @override
   */
  getGroupNameCellColSpan(group) {
    let colspan = super.getGroupNameCellColSpan(group);
    if (this.sh_hasOpenRecordColumn) {
      colspan++;
    }
    return colspan;
  },

  OpenRecord(res_id) {
    var url = window.location.href;
    var latest_url = url + "&id=" + res_id;
    let result = latest_url.replace("view_type=list", "view_type=form");
    window.open(result, "_blank");
  },
});


// Action Menu

patch(ActionMenus.prototype, {
  /**
   * @override
   */

  setup(){
    this.show_open_record_new_tab_button_action = session.sh_enable_open_record_in_new_tab;
    super.setup();
  },

  onOpenRecord() {
    let record_activeIds = this.props.getActiveIds();
    for (var j in record_activeIds) {
      var url = window.location.href;
      var latest_url = url + "&id=" + record_activeIds[j];
      let result = latest_url.replace("view_type=list", "view_type=form");
      window.open(result, "_blank");
    }
  },
});