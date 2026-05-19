/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, useRef } from "@odoo/owl";
import { FileViewer } from "@web/core/file_viewer/file_viewer";

const VIEWER_ID = "commercial.document_file_viewer";

class DocumentPreviewAction extends Component {
    static template = "commercial.DocumentPreviewAction";

    setup() {
        this.rootRef = useRef("root");
        const params = this.props.action.params || {};
        onMounted(() => {
            const attachmentId = params.attachment_id;
            const filename = params.filename || "Document";
            const mimetype = params.mimetype || "application/pdf";
            const rawUrl = "/web/content/" + attachmentId;
            const isPdf = mimetype === "application/pdf";
            const url = isPdf
                ? "/web/static/lib/pdfjs/web/viewer.html?file=" + encodeURIComponent(rawUrl)
                : rawUrl;

            const close = () => {
                try {
                    registry.category("main_components").remove(VIEWER_ID);
                } catch (e) {}
            };

            const file = {
                displayName: filename,
                defaultSource: url,
                downloadUrl: rawUrl + "?download=true",
                isViewable: true,
                isImage: mimetype.startsWith("image/"),
                isPdf: isPdf,
                isVideo: false,
                isText: false,
                isUrlYoutube: false,
                mimetype: mimetype,
            };

            // Supprimer un viewer existant
            try {
                registry.category("main_components").remove(VIEWER_ID);
            } catch (e) {}

            // Ouvrir le FileViewer natif d'Odoo
            registry.category("main_components").add(VIEWER_ID, {
                Component: FileViewer,
                props: { files: [file], startIndex: 0, close },
            });

            // Forcer le FileViewer au-dessus de tous les dialogues
            setTimeout(() => {
                const viewerModal = document.querySelector(".o-FileViewer")?.closest(".modal");
                if (viewerModal) {
                    viewerModal.style.zIndex = "1090";
                }
            }, 50);
        });
    }
}

registry.category("actions").add("commercial.document_preview", DocumentPreviewAction);