
## Job monitoring with grafana

Make a working area
```bash
mkdir -p ~/monitoring
cd ~/monitoring
```

### Set up elasticsearch

```bash
cd ~/monitoring
mkdir elasticsearch
cd elasticsearch
# from https://www.elastic.co/guide/en/elasticsearch/reference/current/targz.html
wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-7.12.1-linux-x86_64.tar.gz
tar -xzf elasticsearch-7.12.1-linux-x86_64.tar.gz
cd elasticsearch-7.12.1/ 

# out of the box default port is 9200
ES_JAVA_OPTS="-Xms3g -Xmx3g" ./bin/elasticsearch
```


### Set up HTCondor job metrics ingestion

Set up the Python virtual environment
```bash
cd ~/monitoring
mkdir ingest
cd ingest

python3 -m venv myenv
source myenv/bin/activate
# make sure to match the installed ES version
pip install "elasticsearch>=7.0.0,<8.0.0" "elasticsearch-dsl>=7.0.0,<8.0.0" pytz tqdm
```

And to test...
```python
from elasticsearch import Elasticsearch
import datetime
es = Elasticsearch("localhost:9200")
response = es.index(
    index="mytest",
    doc_type="docs",
    body={"cpu": 20, "date": datetime.datetime.now()}
)
print(response)
```
The `mytest` index can be dropped later with `curl -X DELETE "localhost:9200/mytest?pretty"`.

Actual ingestion (into the `condor` index) with the [condor.py](ingest/condor.py) script.
```bash
source myenv/bin/activate
for i in `seq 1 10000`; do python condor.py ; sleep 20m; done
```



### Set up grafana

```bash
cd ~/monitoring
mkdir grafana
cd grafana

# run docker container via singularity
GF_SERVER_HTTP_PORT=1234 # out of box default is 3000
singularity run \
    --env GF_AUTH_ANONYMOUS_ENABLED=true \
    --env GF_SERVER_HTTP_PORT=$GF_SERVER_HTTP_PORT \
    --env GF_PATHS_DATA=`pwd` \
    docker://grafana/grafana
# default login is `admin`
```

#### Tweak the UI

* Left panel `Server Admin` > `Users` > change admin password
* Left panel `Configuration` > `Data Sources` > `Elasticsearch`. Change the URL if using a non-standard port. Make this the default data source.
`Index name` = `condor`, `Time field name` = `CompletionDate`. ES `Version` = `7.0+`. `Save & Test`.
* Play around and make dashboards.
* To make a dropdown box to filter by username, `Dashboard settings` > `Variables`, 
then `Type` = `Query`, `Name`/`Label` = `username`, ES `Data source`,
`Query` = `{"find": "terms", "field": "Owner.keyword", "size": 50}`,
and finally make sure that the preview shows some usernames. 
Finally, make sure the `Query` string is `$username` for dashboards where you want to filter by username.

