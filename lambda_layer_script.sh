mkdir tmp
cd tmp
virtualenv v-env
source ./v-env/bin/activate
pip install nltk
deactivate
mkdir python
cd python
cp -r ../v-env/lib64/python3.7/site-packages/* .
cd ..
zip -r nltk_layer.zip python
aws lambda publish-layer-version --layer-name demo-layer --zip-file fileb://nltk_layer.zip --compatible-runtimes python3.7
