from allauth.mfa.adapter import DefaultMFAAdapter

from core import encryption


class MFAAdapter(DefaultMFAAdapter):
    """Keeps the TOTP secret and the recovery-code seed encrypted with the instance key.

    allauth runs every such value through these two hooks and stores what they return; by default
    they return the text unchanged, which leaves the secrets in the database in clear text.
    """

    def encrypt(self, text: str) -> str:
        return encryption.encrypt(text)

    def decrypt(self, encrypted_text: str) -> str:
        return encryption.decrypt(encrypted_text)
