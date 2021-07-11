## Job/storage monitoring with grafana

Make a working area
```bash
mkdir -p ~/monitoring
cd ~/monitoring
```

Grafana and elasticsearch can be run in a GNU screen. Ingestion scripts
can be run in a screen as well, or in a crontab.

### Set up elasticsearch

```bash
cd ~/monitoring
mkdir elasticsearch
cd elasticsearch
```

```bash
# from https://www.elastic.co/guide/en/elasticsearch/reference/current/targz.html
wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-7.12.1-linux-x86_64.tar.gz
tar -xzf elasticsearch-7.12.1-linux-x86_64.tar.gz
cd elasticsearch-7.12.1/ 

# out of the box/default port is 9200
ES_JAVA_OPTS="-Xms3g -Xmx3g" ./bin/elasticsearch -Ehttp.port=9201
```

It could also be setup in a self-contained folder via `singularity` and `docker` with
```bash
PORT=9201
echo -e "path.data:`pwd`\npath.logs:`pwd`\nhttp.port:$PORT" > elasticsearch.yml
echo -e "" > jvm.options
echo -e "property.basePath=`pwd`" > log4j2.properties
singularity run \
    --env ES_JAVA_OPTS="-Xms3g -Xmx3g" \
    --env TINI_SUBREAPER=1 \
    --env ES_PATH_CONF=`pwd` \
    docker://docker.elastic.co/elasticsearch/elasticsearch:7.12.1
```
but note that this is much hackier than the manual download/startup above.


### Set up metrics ingestion

Set up the Python virtual environment
```bash
cd ~/monitoring
mkdir ingest
cd ingest

python3 -m venv myenv
source myenv/bin/activate
# make sure to match the installed ES version
pip install "elasticsearch>=7.0.0,<8.0.0" "elasticsearch-dsl>=7.0.0,<8.0.0" pytz tqdm requests pandas schedule
```

And to test it, make a dummy index and insert a document with python:
```python
from elasticsearch import Elasticsearch
import datetime
es = Elasticsearch("localhost:9201")
response = es.index(
    index="mytest",
    doc_type="docs",
    body={"cpu": 20, "date": datetime.datetime.now()}
)
print(response)
```
or with Bash:
```bash
curl -X POST "localhost:9200/mytest/docs?pretty" -H 'Content-Type: application/json' -d'
{
    "date": "'$(date +%s000)'",
    "cpu": 20
}
'
```

To read it back,
```python
from elasticsearch import Elasticsearch
es = Elasticsearch("localhost:9201")
response = es.search(index="mytest", doc_type="docs", body={})
print(response)
```

or with SQL:
```bash
curl -X POST "localhost:9201/_sql?format=txt" -H 'Content-Type: application/json' -d'{"query":
    "SELECT * FROM mytest ORDER BY cpu DESC LIMIT 5"
# or {"query": "DESCRIBE mytest"} to see the schema
}'
```

To translate compact SQL into native ES, you can do
```bash
curl -X POST "localhost:9201/_sql/translate?pretty" -H 'Content-Type: application/json' -d'{"query": 
    "SELECT * FROM mytest WHERE cpu=10 ORDER BY date DESC LIMIT 1"
}'
```

The `mytest` index can be dropped later with `curl -X DELETE "localhost:9201/mytest?pretty"`.

Actual ingestion into the `condor` index is done with the [condor.py](ingest/condor.py) script
and into the `hadoop` index with the [hadoop.py](ingest/hadoop.py) script. Edit `ingest/config.py` to populate the hadoop namenode
host. There are also a couple more scripts in there for more condor information.

The HTCondor logging script saves a set of classads from completed jobs fetched via `condor_history` since a particular timestamp.
Each time the script is run, this `since` timestamp is calculated as the maximum of the `CompletionDate`
field in the ES database.

```bash
source myenv/bin/activate
python ingest.py
```

### Set up grafana

```bash
cd ~/monitoring
mkdir grafana
cd grafana

# run docker container via singularity
GF_SERVER_HTTP_PORT=50010 # out of box default is 3000
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
* Similarly, add a data source for the `hadoop` index with `Time field name` = `date`.
* Play around and make dashboards.
* To make a dropdown box to filter by username, `Dashboard settings` > `Variables`, 
then `Type` = `Query`, `Name`/`Label` = `username`, ES `Data source`,
`Query` = `{"find": "terms", "field": "Owner.keyword", "size": 50}`,
`Custom all value` = `*`.
and finally make sure that the preview shows some usernames. 
Finally, make sure the `Query` string is `$username` for dashboards where you want to filter by username.

A backup of the latest dashboards are in [grafana/settings](grafana/settings). The `grafana.db` file is in [grafana/](grafana/).

#### Misc commands

* An index can be dumped to json with
```bash
# dump from index `condor` in batches of 10000 and only saving the source document content
# add the document id as a field in the source
singularity exec docker://elasticdump/elasticsearch-dump elasticdump \
    --input=http://localhost:9201/condor \
    --output=condor.jsonl \
    --limit 10000 \
    --sourceOnly \
    --overwrite \
    --noRefresh \
    --transform 'doc._source["jid"] = doc._id;'
```

* Save this into `esql` to shortcut SQL queries.
```bash
#!/usr/bin/env bash

query="$@"
if [ -z "$query" ]; then
    query="show tables"
fi
eshost="localhost:9201"
curl -X POST "$eshost/_sql?format=txt" -H 'Content-Type: application/json' -d'{"query": "'"$query"'"}'
```
If run without any arguments, shows all table names. Can then print table schema with
`esql "describe condor"`, for example.

* Top users by day
```bash
esql "SELECT histogram(CompletionDate, INTERVAL 1 DAY) as h, Owner as n, count(*) as c from condor GROUP BY h,n HAVING c > 2000"
```
* Get list of all unique UCSD T2 node names
```bash
esql "select hostname from condor where Site='UCSDT2' and hostname like '%ucsd%' group by hostname"
```
