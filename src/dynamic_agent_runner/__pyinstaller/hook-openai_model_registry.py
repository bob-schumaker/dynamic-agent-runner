from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)


datas = collect_data_files("openai_model_registry")
datas += copy_metadata("openai-model-registry")
hiddenimports = collect_submodules("tiktoken_ext")
