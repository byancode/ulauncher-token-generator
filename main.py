import uuid
import secrets
import logging
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction

# Loglama ayarı (Hata ayıklama için yararlıdır)
logger = logging.getLogger(__name__)

class TokenGenExtension(Extension):
    def __init__(self):
        super(TokenGenExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        items = []
        
        # 1. UUID v4 Generation
        generated_uuid = str(uuid.uuid4())
        items.append(ExtensionResultItem(
            icon='images/uuid.png',
            name='Generate UUID v4',
            description=f'Copy to clipboard: {generated_uuid}',
            on_enter=CopyToClipboardAction(generated_uuid)
        ))

        # 2. Secure Hex Token (32 characters / 16 bytes)
        hex_token = secrets.token_hex(16)
        items.append(ExtensionResultItem(
            icon='images/token.png',
            name='Generate Hex Token',
            description=f'Secure 32-char hex: {hex_token}',
            on_enter=CopyToClipboardAction(hex_token)
        ))

        # 3. URL-Safe Token (Base64 based)
        url_token = secrets.token_urlsafe(24)
        items.append(ExtensionResultItem(
            icon='images/link.png',
            name='Generate URL-Safe Token',
            description=f'Safe for URLs: {url_token}',
            on_enter=CopyToClipboardAction(url_token)
        ))

        # 4. Short Numeric ID (Optional)
        numeric_id = str(secrets.randbelow(900000) + 100000)
        items.append(ExtensionResultItem(
            icon='images/number.png',
            name='Generate 6-Digit PIN',
            description=f'Random numeric ID: {numeric_id}',
            on_enter=CopyToClipboardAction(numeric_id)
        ))

        return RenderResultListAction(items)

if __name__ == '__main__':
    TokenGenExtension().run()
