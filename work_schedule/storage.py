from whitenoise.storage import CompressedManifestStaticFilesStorage


class ViteAwareStorage(CompressedManifestStaticFilesStorage):
    def hashed_name(self, name, content=None, filename=None):
        if name.startswith("vue/"):
            return name  # Vite already hashes these
        return super().hashed_name(name, content, filename)
