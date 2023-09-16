from android import mActivity, autoclass, activity
from kivy.clock import mainthread


Intent = autoclass('android.content.Intent')


class ShareListener():

    def __init__(self, text_callback=None, video_callback=None):
        self.text_callback = text_callback
        self.intent = mActivity.getIntent()
        self.intent_handler(self.intent)
        activity.bind(on_new_intent=self.intent_handler)

    @mainthread
    def text_callback_on_mainthread(self, file_path, MIME_type):
        self.text_callback(file_path, MIME_type)

    def intent_handler(self, intent):
        action = intent.getAction()
        if Intent.ACTION_SEND == action:
            MIME_type = intent.getType()
            if MIME_type == "text/plain":
                text = intent.getStringExtra(Intent.EXTRA_TEXT)
                if text and self.text_callback:
                    self.text_callback(text, MIME_type)
        elif Intent.ACTION_SEND_MULTIPLE == action:
            MIME_type = intent.getType()
            if MIME_type == "text/plain":
                text = intent.getStringExtra(Intent.EXTRA_TEXT)
                if text and self.text_callback:
                    self.text_callback(text, MIME_type)
