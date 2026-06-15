from PyInstaller.utils.hooks import collect_data_files, copy_metadata


datas = collect_data_files("openai_model_registry")
datas += copy_metadata("openai-model-registry")
