# -*- coding: utf-8 -*-
"""
### A stab at DAG 2 (https://github.com/mblomdahl/o3/issues/13)

Preparation:

* Go to web UI, _Admin_ > _Connections_ > _Create_
* Configure new HDFS type connection with ID `hdfs_default`
* Save it and trigger `o3_d_dag2` manually

What it does:

* Ensures the necessary directories exists in HDFS
* Waits for something to show up in HDFS `/user/airflow/input/` dir
* Moves *.txt files in input dir to HDFS `/user/airflow/processing/`
* Primitive word and row counts in 2 parallel operations
* Prints a summary of word/row counts
* Deletes the processed input file


"""

from os import path
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python_operator import PythonOperator

from o3.sensors.hdfs_sensor import HDFSSensor
from o3.operators.ensure_dir_operator import EnsureDirOperator
from o3.operators.move_file_operator import MoveFileOperator
from o3.operators.word_count_operator import WordCountOperator
from o3.operators.row_count_operator import RowCountOperator
from o3.operators.remove_file_operator import RemoveFileOperator


default_args = {
    'owner': 'mblomdahl',
    'depends_on_past': False,
    'start_date': datetime(2019, 1, 18),
    'email': ['mats.blomdahl@gmail.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(seconds=5),
    # 'queue': 'bash_queue',
    # 'pool': 'backfill',
    # 'priority_weight': 10,
    # 'end_date': datetime(2016, 1, 1),
}

FILE_INPUT_DIR = path.join('/user/airflow/', 'input')

PROCESSING_DIR = path.join('/user/airflow/', 'processing')


with DAG('o3_d_dag2', default_args=default_args, schedule_interval='@once',
         catchup=False) as dag2:

    t0 = EnsureDirOperator(task_id='o3_t_ensure_dirs_exist',
                           paths=[FILE_INPUT_DIR, PROCESSING_DIR],
                           fs_type='hdfs')

    s0 = HDFSSensor(task_id='o3_s_scan_input_dir',
                    hdfs_conn_id='hdfs_default',
                    filepath=FILE_INPUT_DIR)

    t1 = MoveFileOperator(task_id='o3_t_get_input_file',
                          glob_pattern='*.txt',
                          src_dir=FILE_INPUT_DIR,
                          dest_dir=PROCESSING_DIR,
                          fs_type='hdfs',
                          max_files=1,
                          depends_on_past=True)

    def _get_t1_filepaths(**ctx):
        return ctx['ti'].xcom_pull(task_ids='o3_t_get_input_file')

    t2a = WordCountOperator(task_id='o3_t_count_words',
                            filepath=_get_t1_filepaths,
                            fs_type='hdfs')

    t2b = RowCountOperator(task_id='o3_t_count_rows',
                           filepath=_get_t1_filepaths,
                           fs_type='hdfs')

    def _o3_t_summarize(**ctx):
        words, rows = ctx['task_instance'].xcom_pull(
            task_ids=['o3_t_count_words', 'o3_t_count_rows'])
        return f'summary: {words} / {rows}'

    t3 = PythonOperator(task_id='o3_t_summarize',
                        python_callable=_o3_t_summarize,
                        provide_context=True)

    t4 = RemoveFileOperator(task_id='o3_t_remove_input',
                            filepath=_get_t1_filepaths,
                            fs_type='hdfs')

    # Workflow!
    t0 >> s0 >> t1 >> [t2a, t2b] >> t3 >> t4


dag2.doc_md = __doc__
