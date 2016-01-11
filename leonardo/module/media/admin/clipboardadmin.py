
import json
from django.conf import settings
from django.forms.models import modelform_factory
from django.contrib import admin
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .. import settings as media_settings
from ..models import Clipboard, ClipboardItem, Folder
from filer.utils.files import handle_upload, UploadException
from filer.utils.loader import load_object

NO_FOLDER_ERROR = "Can't find folder to upload. Please refresh and try again"
NO_PERMISSIONS_FOR_FOLDER = (
    "Can't use this folder, Permission Denied. Please select another folder."
)


# ModelAdmins
class ClipboardItemInline(admin.TabularInline):
    model = ClipboardItem


class ClipboardAdmin(admin.ModelAdmin):
    model = Clipboard
    inlines = [ClipboardItemInline]
    filter_horizontal = ('files',)
    raw_id_fields = ('user',)
    verbose_name = "DEBUG Clipboard"
    verbose_name_plural = "DEBUG Clipboards"

    def get_urls(self):
        from django.conf.urls import patterns, url
        urls = super(ClipboardAdmin, self).get_urls()
        from .. import views
        url_patterns = patterns('',
                                url(r'^operations/paste_clipboard_to_folder/$',
                                    self.admin_site.admin_view(
                                        views.paste_clipboard_to_folder),
                                    name='filer-paste_clipboard_to_folder'),
                                url(r'^operations/discard_clipboard/$',
                                    self.admin_site.admin_view(
                                        views.discard_clipboard),
                                    name='filer-discard_clipboard'),
                                url(r'^operations/delete_clipboard/$',
                                    self.admin_site.admin_view(
                                        views.delete_clipboard),
                                    name='filer-delete_clipboard'),
                                # upload does it's own permission stuff (because of the stupid
                                # flash missing cookie stuff)
                                url(r'^operations/upload/(?P<folder_id>[0-9]+)/$',
                                    self.ajax_upload,
                                    name='filer-ajax_upload'),
                                url(r'^operations/upload/no_folder/$',
                                    self.ajax_upload,
                                    name='filer-ajax_upload'),
                                )
        url_patterns.extend(urls)
        return url_patterns

    @csrf_exempt
    def ajax_upload(self, request, folder_id=None):
        """
        receives an upload from the uploader. Receives only one file at the time.
        """
        mimetype = "application/json" if request.is_ajax() else "text/html"
        content_type_key = 'content_type'
        response_params = {content_type_key: mimetype}
        folder = None
        if folder_id:
            try:
                # Get folder
                folder = Folder.objects.get(pk=folder_id)
            except Folder.DoesNotExist:
                return HttpResponse(json.dumps({'error': NO_FOLDER_ERROR}),
                                    **response_params)

        # check permissions
        if folder and not folder.has_add_children_permission(request):
            return HttpResponse(
                json.dumps({'error': NO_PERMISSIONS_FOR_FOLDER}),
                **response_params)
        try:
            upload, filename, is_raw = handle_upload(request)

            # Get clipboad
            # TODO: Deprecated/refactor
            # clipboard = Clipboard.objects.get_or_create(user=request.user)[0]

            # find the file type
            for filer_class in media_settings.MEDIA_FILE_MODELS:
                FileSubClass = load_object(filer_class)
                # TODO: What if there are more than one that qualify?
                if FileSubClass.matches_file_type(filename, upload, request):
                    FileForm = modelform_factory(
                        model=FileSubClass,
                        fields=('original_filename', 'owner', 'file')
                    )
                    break
            uploadform = FileForm({'original_filename': filename,
                                   'owner': request.user.pk},
                                  {'file': upload})
            if uploadform.is_valid():
                file_obj = uploadform.save(commit=False)
                # Enforce the FILER_IS_PUBLIC_DEFAULT
                file_obj.is_public = settings.MEDIA_IS_PUBLIC_DEFAULT
                file_obj.folder = folder
                file_obj.save()
                # TODO: Deprecated/refactor
                # clipboard_item = ClipboardItem(
                #    clipboard=clipboard, file=file_obj)
                # clipboard_item.save()
                json_response = {
                    'thumbnail': file_obj.icons['32'],
                    'alt_text': '',
                    'label': str(file_obj),
                    'file_id': file_obj.pk,
                }
                return HttpResponse(json.dumps(json_response),
                                    **response_params)
            else:
                form_errors = '; '.join(['%s: %s' % (
                    field,
                    ', '.join(errors)) for field, errors in list(uploadform.errors.items())
                ])
                raise UploadException(
                    "AJAX request not valid: form invalid '%s'" % (form_errors,))
        except UploadException as e:
            return HttpResponse(json.dumps({'error': str(e)}),
                                **response_params)

    def get_model_perms(self, request):
        """
        It seems this is only used for the list view. NICE :-)
        """
        return {
            'add': False,
            'change': False,
            'delete': False,
        }
