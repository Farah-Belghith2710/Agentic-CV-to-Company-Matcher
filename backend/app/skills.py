"""Skill vocabulary with English/French aliases, groups ("related skills") and implications.

Used by both modes:
  * offline mode: to extract skills from CVs and postings and to judge requirements;
  * LLM mode: to canonicalize LLM output (sklearn -> scikit-learn) and by the verifier,
    which rejects rewritten bullets that mention tools absent from the original bullet.

Alias syntax in the table (prefixes can be combined, e.g. "fr:m:tableaux de bord"):
  "text"     case-insensitive, accent-insensitive phrase (spaces/hyphens are flexible)
  "fr:"      a French alias (written as "AMDEC (FMEA)" when aligning wording, instead of replacing)
  "w:"       a WEAK member: only indirect evidence ("vibration data" for vibration analysis); a CV
             that shows the skill only this way gets "partial", never "met"
  "m:"       a MEMBER of the concept, not a synonym ("Plotly" is data visualization, but the two
             words are not interchangeable). Members count as evidence, but are never swapped
             into a bullet, and a posting that names a member asks for that exact tool.
  "cs:"      case-sensitive token (for short or ambiguous names such as "Excel", "Lean", "AWS")
  "re:..."   raw case-sensitive regex for very short names ("R", "C", "Go")

groups: skills sharing a group are "related" (knowing one partially covers the other).
implies: knowing the skill implies the listed skills (SAP PM -> CMMS).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import fold

_LIST_LEFT = r"(?:(?<=[,/|;(])|(?<=[,/|;(] )|(?<=and )|(?<=et ))"


def _short(tok: str, avoid: str = "") -> list[str]:
    """Regexes for one/two-letter language names that only count inside skill lists."""
    neg = f"(?!{avoid})" if avoid else ""
    return [
        "re:" + _LIST_LEFT + tok + r"(?![\w&'.+#-])" + neg,
        r"re:(?<![\w&.'/-])" + tok + r"(?=\s?[,/|;)])" + neg,
    ]


# (canonical, kind, groups, aliases, implies)
_RAW: list[tuple[str, str, tuple[str, ...], list[str], tuple[str, ...]]] = [
    # --- Programming languages -------------------------------------------------------
    ("Python", "language", ("prog",), ["python", "python3", "fr:langage python"], ()),
    ("R", "language", ("prog", "stats_lang"), ["rstudio", "r programming", "r language", "fr:langage r", "m:tidyverse", "m:ggplot2", "m:r shiny", *_short("R")], ()),
    ("SQL", "language", ("sql",), ["sql", "m:t-sql", "m:pl/sql", "m:plsql"], ()),
    ("Java", "language", ("prog", "jvm"), ["java"], ()),
    ("JavaScript", "language", ("prog",), ["javascript", "ecmascript", "m:es6", "cs:JS"], ()),
    ("TypeScript", "language", ("prog",), ["typescript"], ("JavaScript",)),
    ("C", "language", ("prog", "systems"), ["c programming", "c language", "fr:langage c", "m:ansi c", "m:embedded c", *_short("C")], ()),
    ("C++", "language", ("prog", "systems"), ["c++", "cpp"], ()),
    ("C#", "language", ("prog", "dotnet"), ["c#", "csharp"], ()),
    (".NET", "platform", ("dotnet",), [".net", "dotnet", "m:asp.net", "m:.net core"], ()),
    ("Go", "language", ("prog", "systems"), ["golang", "go language", *_short("Go", r"\s?/\s?[Nn]o")], ()),
    ("Rust", "language", ("prog", "systems"), ["rust programming", "rust language", "rustlang", *_short("Rust")], ()),
    ("Kotlin", "language", ("prog", "jvm"), ["kotlin"], ()),
    ("Swift", "language", ("prog",), ["cs:Swift"], ()),
    ("PHP", "language", ("prog",), ["php", "m:laravel", "m:symfony"], ()),
    ("Ruby", "language", ("prog",), ["m:ruby on rails", "cs:Ruby"], ()),
    ("Scala", "language", ("prog", "jvm"), ["cs:Scala"], ()),
    ("Bash", "language", ("prog", "os"), ["bash", "shell scripting", "m:shell scripts", "m:zsh"], ()),
    ("PowerShell", "language", ("prog",), ["powershell"], ()),
    ("MATLAB", "tool", ("sim", "prog"), ["matlab"], ()),
    ("Simulink", "tool", ("sim",), ["simulink"], ("MATLAB",)),
    ("VBA", "language", ("office",), ["cs:VBA", "visual basic for applications", "m:excel macros", "fr:m:macros excel"], ("Excel",)),
    ("LabVIEW", "tool", ("sim", "automation"), ["labview"], ()),
    # --- Web / backend / frontend ----------------------------------------------------
    ("React", "tool", ("frontend",), ["reactjs", "react.js", "cs:React"], ("JavaScript",)),
    ("Next.js", "tool", ("frontend",), ["next.js", "nextjs"], ("React",)),
    ("Vue.js", "tool", ("frontend",), ["vue.js", "vuejs", "m:nuxt", "cs:Vue"], ("JavaScript",)),
    ("Angular", "tool", ("frontend",), ["angularjs", "cs:Angular"], ("TypeScript",)),
    ("HTML/CSS", "tool", ("markup",), ["m:html", "m:html5", "m:css", "m:css3", "m:sass", "m:scss"], ()),
    ("Tailwind CSS", "tool", ("markup",), ["tailwind", "tailwindcss"], ("HTML/CSS",)),
    ("Node.js", "tool", ("js_backend",), ["node.js", "nodejs", "node js"], ("JavaScript",)),
    ("Express", "tool", ("js_backend",), ["express.js", "expressjs"], ("Node.js",)),
    ("Django", "tool", ("py_web",), ["django"], ("Python",)),
    ("Flask", "tool", ("py_web",), ["cs:Flask"], ("Python",)),
    ("FastAPI", "tool", ("py_web",), ["fastapi"], ("Python",)),
    ("Spring Boot", "tool", ("jvm_web",), ["spring boot", "m:spring framework", "springboot"], ("Java",)),
    ("REST APIs", "concept", ("api",), ["rest api", "rest apis", "restful", "restful apis", "fr:api rest", "fr:apis rest", "w:web services", "fr:w:services web"], ()),
    ("GraphQL", "tool", ("api",), ["graphql"], ()),
    ("WebSockets", "concept", ("api",), ["websocket", "websockets"], ()),
    # --- Testing ---------------------------------------------------------------------
    ("pytest", "tool", ("testing",), ["pytest"], ("Python", "Automated testing")),
    ("Jest", "tool", ("testing",), ["cs:Jest"], ("JavaScript", "Automated testing")),
    ("Cypress", "tool", ("testing",), ["cs:Cypress"], ("Automated testing",)),
    ("Selenium", "tool", ("testing",), ["selenium"], ("Automated testing",)),
    ("Automated testing", "concept", ("testing",), ["automated testing", "test automation", "m:unit testing", "m:unit tests", "m:integration tests", "m:test-driven development", "cs:TDD", "fr:m:tests unitaires", "fr:tests automatises"], ()),
    # --- DevOps / cloud --------------------------------------------------------------
    ("Git", "tool", ("vcs",), ["git", "w:version control", "fr:m:gestion de versions"], ()),
    ("GitHub", "tool", ("vcs",), ["github"], ("Git",)),
    ("GitLab", "tool", ("vcs",), ["gitlab"], ("Git",)),
    ("Docker", "tool", ("containers",), ["docker", "m:docker compose", "m:docker-compose", "m:containerization", "fr:m:conteneurisation"], ()),
    ("Kubernetes", "tool", ("containers",), ["kubernetes", "k8s", "m:helm charts", "cs:Helm"], ()),
    ("Terraform", "tool", ("iac",), ["terraform", "m:infrastructure as code", "cs:IaC"], ()),
    ("Ansible", "tool", ("iac",), ["ansible"], ()),
    ("CI/CD", "concept", ("ci",), ["ci/cd", "ci-cd", "cicd", "m:continuous integration", "m:continuous delivery", "m:continuous deployment", "fr:m:integration continue", "fr:m:deploiement continu"], ()),
    ("GitHub Actions", "tool", ("ci",), ["github actions"], ("CI/CD", "GitHub")),
    ("GitLab CI", "tool", ("ci",), ["gitlab ci", "gitlab-ci"], ("CI/CD", "GitLab")),
    ("Jenkins", "tool", ("ci",), ["cs:Jenkins"], ("CI/CD",)),
    ("Linux", "platform", ("os",), ["linux", "m:ubuntu", "m:debian", "m:centos", "m:red hat"], ()),
    ("Nginx", "tool", ("web_server",), ["nginx"], ()),
    ("Prometheus", "tool", ("monitoring",), ["cs:Prometheus"], ()),
    ("Grafana", "tool", ("monitoring",), ["grafana"], ()),
    ("AWS", "platform", ("cloud",), ["cs:AWS", "amazon web services", "m:aws lambda", "m:amazon s3", "m:amazon ec2"], ()),
    ("Azure", "platform", ("cloud",), ["cs:Azure", "microsoft azure", "m:azure ml", "m:azure devops"], ()),
    ("GCP", "platform", ("cloud",), ["cs:GCP", "google cloud", "google cloud platform"], ()),
    # --- Data engineering ------------------------------------------------------------
    ("Spark", "tool", ("data_eng", "big_data"), ["apache spark", "m:pyspark", "m:spark sql", "cs:Spark"], ()),
    ("Hadoop", "tool", ("data_eng", "big_data"), ["hadoop", "m:hdfs", "m:hive"], ()),
    ("Airflow", "tool", ("data_eng", "orchestration"), ["apache airflow", "cs:Airflow"], ()),
    ("Kafka", "tool", ("data_eng", "streaming"), ["kafka", "apache kafka"], ()),
    ("dbt", "tool", ("data_eng",), ["cs:dbt", "data build tool"], ("SQL",)),
    ("Snowflake", "platform", ("data_eng", "warehouse"), ["cs:Snowflake"], ("SQL",)),
    ("BigQuery", "platform", ("data_eng", "warehouse"), ["bigquery", "big query"], ("SQL",)),
    ("Databricks", "platform", ("data_eng", "big_data"), ["databricks"], ()),
    ("ETL pipelines", "concept", ("data_eng",), ["cs:ETL", "m:cs:ELT", "w:data pipeline", "w:data pipelines", "etl pipelines", "fr:m:pipelines de donnees", "fr:m:pipeline de donnees"], ()),
    ("Data warehousing", "concept", ("data_eng", "warehouse"), ["data warehouse", "data warehousing", "fr:entrepot de donnees", "fr:entrepots de donnees"], ()),
    ("Data modeling", "concept", ("data_eng",), ["data modeling", "data modelling", "fr:modelisation de donnees", "fr:modelisation des donnees", "m:star schema"], ()),
    # --- Databases -------------------------------------------------------------------
    ("PostgreSQL", "tool", ("sql_db",), ["postgresql", "postgres", "m:postgis"], ("SQL",)),
    ("MySQL", "tool", ("sql_db",), ["mysql", "m:mariadb"], ("SQL",)),
    ("SQL Server", "tool", ("sql_db",), ["sql server", "mssql", "ms sql"], ("SQL",)),
    ("Oracle Database", "tool", ("sql_db",), ["oracle database", "oracle db", "oracle sql"], ("SQL",)),
    ("SQLite", "tool", ("sql_db",), ["sqlite"], ("SQL",)),
    ("MongoDB", "tool", ("nosql",), ["mongodb", "mongo db", "cs:Mongo"], ()),
    ("Redis", "tool", ("nosql",), ["redis"], ()),
    ("Elasticsearch", "tool", ("nosql", "search"), ["elasticsearch", "elastic search", "m:opensearch"], ()),
    # --- Data science / ML -----------------------------------------------------------
    ("pandas", "tool", ("py_data",), ["pandas"], ("Python",)),
    ("NumPy", "tool", ("py_data",), ["numpy"], ("Python",)),
    ("SciPy", "tool", ("py_data",), ["scipy"], ("Python",)),
    ("scikit-learn", "tool", ("ml_lib",), ["scikit-learn", "sklearn", "scikit learn"], ("Machine learning", "Python")),
    ("XGBoost", "tool", ("ml_lib", "gbm"), ["xgboost"], ("Machine learning",)),
    ("LightGBM", "tool", ("ml_lib", "gbm"), ["lightgbm", "m:catboost"], ("Machine learning",)),
    ("TensorFlow", "tool", ("dl_framework",), ["tensorflow", "m:tf.keras"], ("Deep learning",)),
    ("Keras", "tool", ("dl_framework",), ["keras"], ("Deep learning",)),
    ("PyTorch", "tool", ("dl_framework",), ["pytorch", "m:pytorch lightning"], ("Deep learning",)),
    ("Machine learning", "concept", ("ml",), ["machine learning", "machine-learning", "fr:apprentissage automatique", "cs:ML", "m:supervised learning", "m:unsupervised learning", "m:random forest", "m:random forests", "m:gradient boosting", "m:classification models", "m:regression models", "fr:m:apprentissage supervise"], ()),
    ("Deep learning", "concept", ("ml", "dl"), ["deep learning", "fr:apprentissage profond", "m:neural networks", "m:neural network", "fr:m:reseaux de neurones", "fr:m:reseau de neurones", "m:cs:LSTM", "m:cs:CNN", "m:cs:CNNs", "m:cs:RNN", "m:transformer models"], ("Machine learning",)),
    ("Computer vision", "concept", ("cv",), ["computer vision", "fr:vision par ordinateur", "m:image processing", "fr:m:traitement d'images", "m:object detection", "m:yolo"], ()),
    ("OpenCV", "tool", ("cv",), ["opencv"], ("Computer vision",)),
    ("NLP", "concept", ("nlp",), ["natural language processing", "cs:NLP", "fr:traitement du langage naturel", "fr:traitement automatique du langage", "m:text mining", "m:text classification", "m:named entity recognition"], ()),
    ("LLMs", "concept", ("genai",), ["large language models", "large language model", "cs:LLM", "cs:LLMs", "m:generative ai", "m:genai", "m:gen ai", "m:prompt engineering", "fr:m:ia generative"], ()),
    ("RAG", "concept", ("genai",), ["retrieval-augmented generation", "retrieval augmented generation", "cs:RAG"], ("LLMs",)),
    ("LangChain", "tool", ("genai",), ["langchain"], ("LLMs",)),
    ("LangGraph", "tool", ("genai",), ["langgraph"], ("LLMs",)),
    ("Vector databases", "tool", ("genai", "search"), ["vector database", "vector databases", "m:faiss", "m:pinecone", "m:qdrant", "m:chroma", "m:chromadb", "m:pgvector", "m:weaviate"], ()),
    ("MLOps", "concept", ("mlops",), ["mlops", "ml ops", "w:model deployment", "m:model monitoring", "fr:m:deploiement de modeles", "fr:m:deploiement des modeles"], ()),
    ("MLflow", "tool", ("mlops",), ["mlflow"], ("MLOps",)),
    ("Feature engineering", "concept", ("ml",), ["feature engineering", "fr:ingenierie des caracteristiques", "m:feature selection"], ("Machine learning",)),
    ("Statistics", "concept", ("stats",), ["statistics", "statistical analysis", "fr:statistiques", "fr:statistique", "fr:analyse statistique", "m:statistical modeling", "m:statistical modelling", "m:hypothesis testing", "fr:m:tests statistiques", "m:inferential statistics", "m:regression analysis", "m:bayesian statistics"], ()),
    ("Time series analysis", "concept", ("time_series",), ["time series", "time-series", "time series analysis", "fr:series temporelles", "fr:serie temporelle", "fr:series chronologiques", "m:arima", "m:sarima"], ()),
    ("Forecasting", "concept", ("time_series",), ["forecasting", "m:demand forecasting", "fr:prevision", "fr:previsions", "m:prophet"], ()),
    ("Anomaly detection", "concept", ("time_series",), ["anomaly detection", "m:outlier detection", "fr:detection d'anomalies", "fr:detection d'anomalie", "fr:detection des anomalies", "m:isolation forest"], ()),
    ("Survival analysis", "method", ("life_data", "stats"), ["survival analysis", "fr:analyse de survie", "m:kaplan-meier", "m:kaplan meier", "m:cox model", "m:cox proportional hazards"], ()),
    ("Remaining useful life", "method", ("life_data", "pdm"), ["remaining useful life", "cs:RUL", "fr:duree de vie residuelle", "fr:duree de vie utile restante"], ("Predictive maintenance",)),
    ("A/B testing", "method", ("stats",), ["a/b testing", "a/b tests", "ab testing", "split testing", "w:experimentation"], ()),
    ("Causal inference", "method", ("stats",), ["causal inference", "m:causal modeling", "m:uplift modeling"], ()),
    ("Monte Carlo simulation", "method", ("stats", "sim"), ["monte carlo", "monte-carlo"], ()),
    ("Operations research", "method", ("math",), ["operations research", "fr:recherche operationnelle", "m:linear programming", "fr:m:programmation lineaire", "m:mixed-integer programming", "m:cs:MILP", "m:gurobi", "m:or-tools"], ()),
    ("Data analysis", "concept", ("analytics",), ["data analysis", "data analytics", "fr:analyse de donnees", "fr:analyse des donnees", "m:exploratory data analysis", "m:cs:EDA", "m:data cleaning", "fr:m:nettoyage de donnees", "fr:m:nettoyage des donnees"], ()),
    ("Data visualization", "concept", ("viz",), ["data visualization", "data visualisation", "dataviz", "fr:visualisation de donnees", "fr:visualisation des donnees", "m:matplotlib", "m:seaborn", "m:plotly", "m:dashboards", "m:dashboarding", "fr:m:tableaux de bord", "fr:m:tableau de bord"], ()),
    ("Business intelligence", "domain", ("bi",), ["business intelligence", "cs:BI", "fr:informatique decisionnelle", "fr:m:decisionnel"], ()),
    ("Power BI", "tool", ("bi", "viz"), ["power bi", "powerbi", "m:dax"], ("Data visualization", "Business intelligence")),
    ("Tableau", "tool", ("bi", "viz"), ["tableau software", "tableau desktop", "re:Tableau(?! de bord)(?![\\w])"], ("Data visualization", "Business intelligence")),
    ("Looker", "tool", ("bi", "viz"), ["cs:Looker", "m:looker studio", "m:google data studio"], ("Data visualization", "Business intelligence")),
    ("Power Query", "tool", ("bi", "office"), ["power query"], ()),
    ("Excel", "tool", ("office",), ["cs:Excel", "cs:EXCEL", "microsoft excel", "ms excel", "m:advanced excel", "fr:m:excel avance", "m:pivot tables", "fr:m:tableaux croises dynamiques"], ()),
    ("SAS", "tool", ("stats_lang",), ["sas programming", "sas base", "m:sas enterprise guide"], ()),
    ("Minitab", "tool", ("stats_lang", "quality"), ["minitab"], ("Statistics",)),
    ("JMP", "tool", ("stats_lang",), ["cs:JMP"], ("Statistics",)),
    # --- Reliability engineering -----------------------------------------------------
    ("Reliability engineering", "domain", ("reliability",), ["reliability engineering", "fr:ingenierie de la fiabilite", "fr:fiabilite", "m:reliability analysis", "m:reliability analyses", "m:reliability studies", "m:reliability improvement", "m:equipment reliability", "m:asset reliability", "m:system reliability", "fr:m:etudes de fiabilite", "fr:m:analyse de fiabilite", "fr:m:surete de fonctionnement", "m:dependability", "m:cs:RAMS", "m:reliability, availability and maintainability"], ()),
    ("FMEA", "method", ("risk_analysis",), ["fmea", "fmeca", "m:pfmea", "m:dfmea", "fr:amdec", "fr:amde", "failure mode and effects analysis", "failure modes and effects analysis", "failure mode, effects and criticality analysis", "failure mode effects and criticality analysis", "fr:analyse des modes de defaillance"], ("Reliability engineering",)),
    ("Fault tree analysis", "method", ("risk_analysis", "sys_rel"), ["fault tree analysis", "fault tree", "fault trees", "cs:FTA", "fr:arbre de defaillance", "fr:arbres de defaillance", "fr:arbre des defaillances", "fr:arbre de defaillances", "fr:arbres de defaillances"], ("Reliability engineering",)),
    ("Reliability block diagrams", "method", ("sys_rel",), ["reliability block diagram", "reliability block diagrams", "cs:RBD", "cs:RBDs", "fr:diagramme de fiabilite", "fr:diagrammes de fiabilite", "fr:diagramme de blocs de fiabilite"], ("Reliability engineering",)),
    ("Markov models", "method", ("sys_rel",), ["markov chain", "markov chains", "markov model", "markov models", "markov process", "fr:chaines de markov", "fr:chaine de markov", "fr:processus de markov"], ()),
    ("Weibull analysis", "method", ("life_data",), ["weibull", "weibull analysis", "fr:loi de weibull", "fr:analyse de weibull", "m:life data analysis", "fr:m:analyse de duree de vie"], ("Reliability engineering",)),
    ("MTBF", "concept", ("maint_kpi",), ["mtbf", "mean time between failures", "m:mttf", "m:mean time to failure", "fr:temps moyen entre pannes", "fr:moyenne des temps de bon fonctionnement"], ()),
    ("MTTR", "concept", ("maint_kpi",), ["mttr", "mean time to repair", "fr:temps moyen de reparation"], ()),
    ("OEE", "concept", ("maint_kpi", "lean"), ["cs:OEE", "fr:cs:TRS", "overall equipment effectiveness", "fr:taux de rendement synthetique"], ()),
    ("Maintenance KPIs", "concept", ("maint_kpi",), ["maintenance kpis", "maintenance kpi", "maintenance metrics", "fr:indicateurs de maintenance", "fr:indicateurs de performance de la maintenance", "fr:m:taux de disponibilite", "m:availability rate", "m:equipment availability"], ()),
    ("RCM", "method", ("maint_strategy",), ["cs:RCM", "reliability-centered maintenance", "reliability centered maintenance", "reliability-centred maintenance", "reliability centred maintenance", "fr:maintenance basee sur la fiabilite", "fr:cs:MBF"], ("Reliability engineering",)),
    ("TPM", "method", ("maint_strategy", "lean"), ["cs:TPM", "total productive maintenance", "fr:maintenance productive totale", "m:autonomous maintenance", "fr:m:maintenance autonome"], ()),
    ("Preventive maintenance", "method", ("maint_strategy",), ["preventive maintenance", "fr:maintenance preventive", "planned maintenance", "fr:maintenance planifiee", "fr:maintenance systematique", "m:preventive maintenance plans", "m:cs:PM plans"], ()),
    ("Predictive maintenance", "method", ("maint_strategy", "pdm"), ["predictive maintenance", "fr:maintenance predictive", "cs:PdM", "m:prognostics", "fr:m:pronostic", "m:prognostics and health management", "m:cs:PHM"], ()),
    ("Condition monitoring", "method", ("cm", "pdm"), ["condition monitoring", "condition-based maintenance", "condition based maintenance", "fr:maintenance conditionnelle", "fr:surveillance conditionnelle", "cs:CBM", "m:machine health monitoring", "m:asset health monitoring", "fr:m:surveillance de l'etat"], ()),
    ("Vibration analysis", "method", ("cm",), ["vibration analysis", "vibration monitoring", "vibration diagnostics", "fr:analyse vibratoire", "fr:analyse des vibrations", "fr:analyses vibratoires", "w:vibration data", "fr:w:donnees vibratoires", "m:fft spectrum"], ("Condition monitoring",)),
    ("Thermography", "method", ("cm",), ["thermography", "infrared thermography", "fr:thermographie", "fr:thermographie infrarouge", "m:thermal imaging"], ("Condition monitoring",)),
    ("Oil analysis", "method", ("cm",), ["oil analysis", "lubricant analysis", "fr:analyse d'huile", "fr:analyse des huiles", "m:tribology", "fr:m:tribologie"], ("Condition monitoring",)),
    ("Non-destructive testing", "method", ("cm", "inspection"), ["non-destructive testing", "non destructive testing", "cs:NDT", "fr:controle non destructif", "fr:controles non destructifs", "fr:cs:CND", "m:ultrasonic testing", "m:ultrasound testing", "fr:m:controle par ultrasons"], ()),
    ("Root cause analysis", "method", ("problem_solving",), ["root cause analysis", "root-cause analysis", "cs:RCA", "fr:analyse des causes racines", "fr:causes racines", "fr:cause racine", "w:root cause", "m:5 whys", "m:five whys", "fr:m:5 pourquoi", "m:ishikawa", "m:fishbone diagram", "m:cs:8D", "m:failure analysis", "fr:m:analyse de defaillance", "fr:m:analyse des defaillances", "fr:m:analyse des pannes"], ()),
    ("CMMS", "tool", ("cmms",), ["cs:CMMS", "fr:cs:GMAO", "computerized maintenance management", "computerised maintenance management", "fr:gestion de maintenance assistee par ordinateur", "maintenance management system", "m:cs:EAM"], ()),
    ("SAP PM", "tool", ("cmms", "erp"), ["sap pm", "sap plant maintenance", "sap-pm", "sap maintenance"], ("CMMS", "SAP")),
    ("IBM Maximo", "tool", ("cmms",), ["maximo", "ibm maximo"], ("CMMS",)),
    ("SAP", "tool", ("erp",), ["cs:SAP", "m:sap s/4hana", "m:sap erp", "m:s/4hana"], ()),
    ("Maintenance planning", "method", ("maint_mgmt",), ["maintenance planning", "maintenance scheduling", "fr:planification de la maintenance", "fr:planification maintenance", "fr:ordonnancement de la maintenance", "m:work order management", "w:work orders", "fr:w:ordres de travail", "fr:m:plan de maintenance", "fr:m:plans de maintenance", "m:maintenance plan", "m:maintenance plans"], ()),
    ("Spare parts management", "method", ("maint_mgmt",), ["spare parts management", "w:spare parts", "fr:gestion des pieces de rechange", "fr:w:pieces de rechange", "fr:w:pieces detachees", "m:critical spares"], ()),
    ("Asset management", "domain", ("asset",), ["asset management", "fr:gestion des actifs", "m:asset integrity", "m:asset lifecycle", "fr:m:integrite des equipements", "fr:m:gestion des equipements"], ()),
    ("ISO 55000", "standard", ("asset", "standards"), ["iso 55000", "iso 55001", "iso55000", "iso55001"], ("Asset management",)),
    ("Rotating equipment", "domain", ("mech",), ["rotating equipment", "rotating machinery", "fr:machines tournantes", "m:pumps and compressors", "fr:m:pompes et compresseurs", "w:bearings", "fr:w:roulements", "w:gearboxes", "fr:w:reducteurs", "m:centrifugal pumps", "fr:m:pompes centrifuges"], ()),
    ("Hydraulics & pneumatics", "domain", ("mech",), ["m:hydraulics", "m:hydraulic systems", "fr:m:hydraulique", "m:pneumatics", "m:pneumatic systems", "fr:m:pneumatique", "fr:m:electropneumatique"], ()),
    ("Mechanical maintenance", "domain", ("mech", "maint_trade"), ["mechanical maintenance", "fr:maintenance mecanique", "w:lubrication", "fr:w:lubrification", "fr:w:graissage"], ()),
    ("Electrical maintenance", "domain", ("elec", "maint_trade"), ["electrical maintenance", "fr:maintenance electrique", "fr:m:electrotechnique", "m:electrotechnics", "w:electrical systems", "m:variable frequency drives", "m:cs:VFD", "m:cs:VFDs", "fr:m:variateurs de vitesse"], ()),
    # --- Industrial automation / IoT -------------------------------------------------
    ("PLC programming", "tool", ("automation",), ["cs:PLC", "cs:PLCs", "programmable logic controller", "programmable logic controllers", "plc programming", "fr:automate programmable", "fr:automates programmables", "fr:m:automatisme", "fr:m:automatismes", "m:ladder logic", "m:grafcet"], ()),
    ("Siemens TIA Portal", "tool", ("automation",), ["tia portal", "m:step 7", "m:step7", "m:simatic", "m:s7-1200", "m:s7-1500", "m:s7-300"], ("PLC programming",)),
    ("Rockwell Studio 5000", "tool", ("automation",), ["studio 5000", "m:rslogix", "m:allen-bradley", "m:allen bradley", "m:controllogix"], ("PLC programming",)),
    ("SCADA/HMI", "tool", ("automation",), ["m:cs:SCADA", "m:cs:HMI", "fr:m:cs:IHM", "m:wincc", "fr:m:supervision industrielle", "m:intouch", "m:human-machine interface", "m:human machine interface"], ()),
    ("Industrial protocols", "concept", ("automation", "iot"), ["m:modbus", "m:profinet", "m:profibus", "m:opc ua", "m:opc-ua", "m:ethernet/ip", "m:can bus", "m:canbus", "industrial protocols"], ()),
    ("IoT", "domain", ("iot",), ["cs:IoT", "internet of things", "fr:internet des objets", "fr:objets connectes", "m:cs:IIoT", "m:industrial iot", "m:industrial internet of things"], ()),
    ("MQTT", "tool", ("iot",), ["mqtt"], ("IoT",)),
    ("Embedded boards", "tool", ("iot", "embedded"), ["m:arduino", "m:raspberry pi", "m:esp32", "m:stm32"], ()),
    ("Embedded systems", "domain", ("embedded",), ["embedded systems", "embedded software", "fr:systemes embarques", "fr:systeme embarque", "m:firmware", "m:microcontrollers", "fr:m:microcontroleurs"], ()),
    ("Sensors & instrumentation", "domain", ("iot", "cm"), ["w:sensors", "w:sensor data", "fr:w:capteurs", "w:instrumentation", "m:data acquisition", "fr:m:acquisition de donnees", "m:cs:DAQ", "m:accelerometers", "fr:m:accelerometres"], ()),
    ("Digital twin", "concept", ("sim",), ["digital twin", "digital twins", "fr:jumeau numerique", "fr:jumeaux numeriques"], ()),
    # --- Mechanical design / simulation ----------------------------------------------
    ("SolidWorks", "tool", ("cad",), ["solidworks", "solid works"], ("Mechanical design",)),
    ("CATIA", "tool", ("cad",), ["catia"], ("Mechanical design",)),
    ("AutoCAD", "tool", ("cad",), ["autocad"], ()),
    ("Autodesk Inventor", "tool", ("cad",), ["autodesk inventor", "cs:Inventor"], ("Mechanical design",)),
    ("Creo", "tool", ("cad",), ["ptc creo", "cs:Creo"], ("Mechanical design",)),
    ("Fusion 360", "tool", ("cad",), ["fusion 360"], ("Mechanical design",)),
    ("Mechanical design", "domain", ("cad", "mech"), ["mechanical design", "machine design", "fr:conception mecanique", "fr:m:dessin industriel", "m:technical drawing", "m:technical drawings", "fr:m:dessin technique"], ()),
    ("GD&T", "method", ("cad",), ["gd&t", "geometric dimensioning and tolerancing", "fr:cotation fonctionnelle", "m:iso gps"], ()),
    ("Finite element analysis", "method", ("sim",), ["finite element analysis", "finite element method", "finite elements", "cs:FEA", "cs:FEM", "fr:elements finis", "fr:methode des elements finis", "fr:m:calcul de structures"], ()),
    ("ANSYS", "tool", ("sim",), ["ansys"], ("Finite element analysis",)),
    ("Abaqus", "tool", ("sim",), ["abaqus"], ("Finite element analysis",)),
    ("COMSOL", "tool", ("sim",), ["comsol"], ()),
    ("Discrete-event simulation", "method", ("sim",), ["discrete event simulation", "discrete-event simulation", "fr:simulation a evenements discrets", "m:flexsim", "m:anylogic", "m:arena simulation"], ()),
    # --- Quality / lean / safety -----------------------------------------------------
    ("Lean manufacturing", "method", ("lean",), ["lean manufacturing", "lean management", "lean production", "cs:Lean", "m:lean six sigma", "m:value stream mapping", "m:cs:VSM", "m:kaizen", "m:cs:5S", "m:cs:SMED", "m:poka-yoke", "m:poka yoke", "fr:w:amelioration continue", "w:continuous improvement"], ()),
    ("Six Sigma", "method", ("quality", "stats"), ["six sigma", "6 sigma", "m:lean six sigma", "m:dmaic", "m:green belt", "m:black belt", "m:yellow belt"], ()),
    ("SPC", "method", ("quality", "stats"), ["cs:SPC", "fr:cs:MSP", "statistical process control", "fr:maitrise statistique des procedes", "m:control charts", "fr:m:cartes de controle", "m:process capability", "m:capability analysis", "m:cs:Cpk"], ()),
    ("ISO 9001", "standard", ("quality", "standards"), ["iso 9001", "iso9001", "m:quality management system", "m:cs:QMS", "fr:m:cs:SMQ", "fr:m:systeme de management de la qualite"], ()),
    ("IATF 16949", "standard", ("quality", "standards"), ["iatf 16949", "cs:IATF", "ts 16949"], ()),
    ("ISO 14001", "standard", ("standards", "hse"), ["iso 14001", "iso14001"], ()),
    ("ISO 45001", "standard", ("standards", "hse"), ["iso 45001", "iso45001", "m:ohsas 18001"], ()),
    ("HAZOP", "method", ("risk_analysis", "safety"), ["cs:HAZOP", "hazard and operability"], ()),
    ("Functional safety", "domain", ("safety",), ["functional safety", "fr:securite fonctionnelle", "m:iec 61508", "m:iec 61511", "m:iso 26262", "m:iso 13849", "m:arp4761", "m:cs:SIL", "m:safety integrity level"], ()),
    ("Risk assessment", "method", ("risk_analysis", "safety"), ["risk assessment", "risk assessments", "risk analysis", "m:risk management", "fr:analyse des risques", "fr:evaluation des risques", "fr:m:gestion des risques", "fr:analyse de risques"], ()),
    ("ATEX", "standard", ("safety",), ["cs:ATEX"], ()),
    ("Lockout/tagout", "method", ("safety",), ["lockout/tagout", "lockout tagout", "lock-out tag-out", "cs:LOTO", "fr:consignation", "fr:consignation/deconsignation"], ()),
    ("HSE", "domain", ("hse", "safety"), ["cs:HSE", "m:cs:QHSE", "m:health and safety", "fr:m:hygiene securite environnement", "fr:m:sante et securite"], ()),
    # --- Project / ways of working ---------------------------------------------------
    ("Project management", "method", ("pm",), ["project management", "fr:gestion de projet", "fr:gestion de projets", "fr:management de projet", "m:cs:PMP", "m:ms project", "m:microsoft project", "m:gantt chart", "m:gantt charts", "fr:m:diagramme de gantt"], ()),
    ("Agile/Scrum", "method", ("pm",), ["cs:Agile", "agile methodology", "agile methodologies", "agile development", "agile environment", "agile teams", "m:scrum", "fr:methodes agiles", "fr:methode agile", "fr:methodologie agile"], ()),
    ("Jira", "tool", ("pm",), ["jira", "m:confluence"], ()),
    ("Zendesk", "tool", ("support",), ["zendesk"], ()),
]


@dataclass
class Skill:
    name: str
    kind: str
    groups: tuple[str, ...]
    implies: tuple[str, ...]
    fr_aliases: set[str] = field(default_factory=set)  # normalized keys
    member_aliases: set[str] = field(default_factory=set)  # normalized keys (ci) or exact tokens (cs)
    weak_aliases: set[str] = field(default_factory=set)


SKILLS: dict[str, Skill] = {}
_CI_ALIAS: dict[str, list[str]] = {}  # normalized folded alias -> canonical names
_CS_ALIAS: dict[str, list[str]] = {}  # case-sensitive alias -> canonical names
_CI_SPACED: set[str] = set()  # folded aliases with single spaces, for the regex
_REGEX: list[tuple[re.Pattern[str], str]] = []


def _norm_alias(s: str) -> str:
    """Lookup key: folded, separators removed ('Power-BI' == 'power bi' == 'powerbi')."""
    return re.sub(r"[\s\-]+", "", fold(s).strip())


def _spaced(s: str) -> str:
    return re.sub(r"[\s\-]+", " ", fold(s).strip())


def _trie_regex(words: list[str], flexible_space: bool) -> str:
    """Compile many literal words into one prefix-sharing regex (fast even with 1000 aliases)."""
    trie: dict = {}
    for w in words:
        node = trie
        for ch in w:
            node = node.setdefault(ch, {})
        node[""] = True

    def build(node: dict) -> str:
        children = sorted(k for k in node if k)
        alts = []
        for ch in children:
            piece = r"[\s\-]*" if (flexible_space and ch == " ") else re.escape(ch)
            alts.append(piece + build(node[ch]))
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"
        return "(?:" + body + ")?" if "" in node else body

    return build(trie)


# Canonical names that are ordinary words (or too short) are matched only through their aliases.
_NAME_NOT_ALIAS = {
    "R", "C", "Go", "Excel", "Rust", "Swift", "Scala", "Ruby", "Spark", "React", "Angular", "Flask", "Jest",
    "Cypress", "Jenkins", "Prometheus", "SAP", "Looker", "Snowflake", "Tableau", "dbt", "SAS", "Azure", "Creo",
    "RAG", "Express", "Agile/Scrum", "JMP", "Lean manufacturing", "Airflow", "HTML/CSS", "Hydraulics & pneumatics",
    "Sensors & instrumentation", "Embedded boards", "SCADA/HMI", "OEE", "CMMS",
}

for _name, _kind, _groups, _aliases, _implies in _RAW:
    sk = Skill(_name, _kind, _groups, _implies)
    SKILLS[_name] = sk
    for al in list(_aliases) if _name in _NAME_NOT_ALIAS else [_name, *_aliases]:
        if al.startswith("re:"):
            _REGEX.append((re.compile(al[3:]), _name))
            continue
        is_fr = is_member = is_cs = is_weak = False
        while True:
            if al.startswith("fr:"):
                is_fr, al = True, al[3:]
            elif al.startswith("m:"):
                is_member, al = True, al[2:]
            elif al.startswith("w:"):
                is_member, is_weak, al = True, True, al[2:]
            elif al.startswith("cs:"):
                is_cs, al = True, al[3:]
            else:
                break
        if is_cs:
            _CS_ALIAS.setdefault(al, []).append(_name)
            if is_fr:
                sk.fr_aliases.add(al)
            if is_member:
                sk.member_aliases.add(al)
            if is_weak:
                sk.weak_aliases.add(al)
            continue
        key = _norm_alias(al)
        _CI_SPACED.add(_spaced(al))
        if _name not in _CI_ALIAS.setdefault(key, []):
            _CI_ALIAS[key].append(_name)
        if is_fr:
            sk.fr_aliases.add(key)
        if is_member:
            sk.member_aliases.add(key)
        if is_weak:
            sk.weak_aliases.add(key)

_CI_RE = re.compile(r"(?<![\w])" + _trie_regex(sorted(_CI_SPACED), True) + r"(?![\w+#])")
_CS_RE = re.compile(r"(?<![\w])" + _trie_regex(sorted(_CS_ALIAS), False) + r"(?![\w+#])")


@dataclass
class SkillHit:
    skill: str
    start: int
    end: int
    surface: str  # the text exactly as written
    french: bool = False
    member: bool = False  # a specific member of the concept, not a synonym of it
    weak: bool = False  # indirect evidence only

    @property
    def key(self) -> str:
        return _norm_alias(self.surface)


def find_skills(text: str) -> list[SkillHit]:
    """Return every skill mention in `text` (positions refer to `text`)."""
    hits: list[SkillHit] = []
    folded = fold(text)
    for m in _CI_RE.finditer(folded):
        key = re.sub(r"[\s\-]+", "", m.group(0))
        for name in _CI_ALIAS.get(key, []):
            sk = SKILLS[name]
            hits.append(SkillHit(name, m.start(), m.end(), text[m.start(): m.end()], key in sk.fr_aliases, key in sk.member_aliases, key in sk.weak_aliases))
    for m in _CS_RE.finditer(text):
        tok = m.group(0)
        for name in _CS_ALIAS.get(tok, []):
            sk = SKILLS[name]
            hits.append(SkillHit(name, m.start(), m.end(), tok, tok in sk.fr_aliases, tok in sk.member_aliases, tok in sk.weak_aliases))
    for rx, name in _REGEX:
        for m in rx.finditer(text):
            hits.append(SkillHit(name, m.start(), m.end(), m.group(0)))
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    seen: set[tuple[str, int]] = set()
    unique = []
    for h in hits:
        if (h.skill, h.start) not in seen:
            seen.add((h.skill, h.start))
            unique.append(h)
    return unique


def skills_in(text: str) -> set[str]:
    return {h.skill for h in find_skills(text)}


def with_implied(names: set[str]) -> dict[str, str | None]:
    """Expand a skill set with implied skills. Returns {skill: implied_by or None}."""
    out: dict[str, str | None] = {n: None for n in names}
    frontier = list(names)
    while frontier:
        cur = frontier.pop()
        sk = SKILLS.get(cur)
        if not sk:
            continue
        for imp in sk.implies:
            if imp not in out:
                out[imp] = out[cur] or cur
                frontier.append(imp)
    return out


def canonical(term: str) -> str | None:
    """Map any alias ('sklearn', 'AMDEC', 'Power-BI') to its canonical name, if known."""
    term = term.strip()
    if not term:
        return None
    if term in SKILLS:
        return term
    hits = [h for h in find_skills(term) if h.end - h.start >= len(term.strip()) * 0.6]
    if hits:
        return hits[0].skill
    for name in SKILLS:
        if fold(name) == fold(term):
            return name
    return None


def related(a: str, b: str) -> bool:
    sa, sb = SKILLS.get(a), SKILLS.get(b)
    if not sa or not sb or a == b:
        return False
    return bool(set(sa.groups) & set(sb.groups))


def is_french_surface(skill: str, surface: str) -> bool:
    sk = SKILLS.get(skill)
    return bool(sk and (_norm_alias(surface) in sk.fr_aliases or surface in sk.fr_aliases))


def norm_key(surface: str) -> str:
    return _norm_alias(surface)


# --- Human languages -------------------------------------------------------------------
LANGUAGES: dict[str, list[str]] = {
    "English": ["english", "anglais", "englisch", "ingles", "englischkenntnisse"],
    "French": ["french", "francais", "franzosisch", "frances", "franzosischkenntnisse"],
    "Arabic": ["arabic", "arabe", "arabisch"],
    "German": ["german", "allemand", "deutsch", "aleman", "deutschkenntnisse"],
    "Spanish": ["spanish", "espagnol", "espanol", "spanisch"],
    "Italian": ["italian", "italien", "italienisch"],
    "Portuguese": ["portuguese", "portugais"],
    "Dutch": ["dutch", "neerlandais", "niederlandisch"],
    "Turkish": ["turkish", "turc", "turkisch"],
    "Chinese": ["chinese", "mandarin", "chinois"],
    "Japanese": ["japanese", "japonais"],
}
_LANG_RE = re.compile(r"(?<![\w])(" + "|".join(a for v in LANGUAGES.values() for a in v) + r")(?![\w])")
_LANG_LOOKUP = {a: k for k, v in LANGUAGES.items() for a in v}

LEVELS = [  # (pattern on folded text, numeric level 1..5)
    (r"\b(native|mother tongue|langue maternelle|maternelle|natif|native speaker|muttersprache)\b", 5),
    (r"\b(c2|bilingual|bilingue|fluent|fluently|courant|couramment|fliessend|proficient|full professional|sehr gute?)\b", 4),
    (r"\b(c1|advanced|avance|professional working|professionnel)\b", 4),
    (r"\b(b2|upper[- ]intermediate|good command|bonne maitrise|bon niveau|gute)\b", 3),
    (r"\b(b1|intermediate|intermediaire|working knowledge)\b", 2),
    (r"\b(a1|a2|basic|basics|notions|elementary|beginner|debutant|scolaire)\b", 1),
]


def find_languages(text: str) -> dict[str, int]:
    """Human languages mentioned in `text` with an estimated level (1 basic .. 5 native, 3 if unknown)."""
    folded = fold(text)
    matches = list(_LANG_RE.finditer(folded))
    out: dict[str, int] = {}
    stops = re.compile(r"[\n;|•]")
    for i, m in enumerate(matches):
        lang = _LANG_LOOKUP[m.group(1)]
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(folded)
        prev = matches[i - 1].end() if i > 0 else 0
        after = folded[m.end(): nxt]
        stop = stops.search(after)
        after = after[: stop.start()] if stop else after
        before = folded[prev: m.start()]
        cut = max(before.rfind(c) for c in "\n;|•")
        before = before[cut + 1:] if cut >= 0 else before
        level = 3
        for window in (after[:60], before[-40:]):
            found = next((lvl for pat, lvl in LEVELS if re.search(pat, window)), None)
            if found:
                level = found
                break
        out[lang] = max(out.get(lang, 0), level)
    return out


_FUNCTION_WORDS = {"de", "des", "du", "d", "la", "le", "les", "l", "of", "the", "a", "an", "and", "et", "en"}


def same_wording(cv: str, jd: str) -> bool:
    """True when the CV already uses the posting's wording, give or take articles, plurals or extra
    words on the CV side ('Excel avancé' covers 'Excel'; 'modélisation des données' = 'de données').
    Not symmetric: 'Postgres' does NOT cover 'PostgreSQL', so that one is worth aligning."""

    def key(x: str) -> str:
        words = [w for w in re.split(r"[\s\-']+", fold(x)) if w and w not in _FUNCTION_WORDS]
        return "".join(words)

    kc, kj = key(cv), key(jd)
    if not kc or not kj:
        return False
    if kc == kj or kj in kc:
        return True
    n = 0
    for x, y in zip(kc, kj):
        if x != y:
            break
        n += 1
    return abs(len(kc) - len(kj)) <= 1 and n >= 0.75 * min(len(kc), len(kj))
