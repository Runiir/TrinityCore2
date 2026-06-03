WE use dvc for `dataset/` folder
```sh
pixi run dvc-add-dataset
git add dataset.dvc .gitignore
git commit -m "Update dataset"
pixi run dvc-push
```