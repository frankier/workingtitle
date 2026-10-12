from workingtitle.devserver import ReloadSpec, run_server
from web_assets import ASSETS

if __name__ == "__main__":
    run_server("app:app", assets=ASSETS, reload=ReloadSpec(), port=8000)
