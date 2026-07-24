from whitenoise.storage import CompressedManifestStaticFilesStorage


class SafeManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Some vendor CSS (e.g. bootstrap) ships alongside .css.map sourcemaps that
    reference each other, which can exceed ManifestStaticFilesStorage's default
    post-process pass limit. Give it more room to converge.
    """
    max_post_process_passes = 10
