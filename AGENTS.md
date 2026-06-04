Use pixi for python related stuff.
Use DVC/DVCLive for experiment tracking.
Commit experiment code/configs to git, and checkpoint generated data/artifacts with DVC.
After future experiments, run dvc status and dvc push to keep the remote in sync.
