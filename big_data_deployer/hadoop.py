#!/usr/bin/env python2

from __future__ import print_function
from .frameworkmanager import Framework, FrameworkVersion, FrameworkRegistry, get_framework_registry
from . import util
import glob
import os.path
import re

_SETTING_JAVA_HOME = "java_home"
_SETTING_YARN_MB = "yarn_memory_mb"
_SETTING_LOG_AGGREGATION = "log_aggregation"
_ALL_SETTINGS = [
    (_SETTING_JAVA_HOME, "value of JAVA_HOME to deploy Hadoop with"),
    (_SETTING_YARN_MB, "memory available per node to YARN in MB"),
    (_SETTING_LOG_AGGREGATION, "enable YARN log aggregation")
]

_DEFAULT_YARN_MB = 4096
_DEFAULT_LOG_AGGREGATION = False

class HadoopFrameworkVersion(FrameworkVersion):
    def __init__(self, version, archive_url, archive_extension, archive_root_dir, template_dir):
        super(HadoopFrameworkVersion, self).__init__(version, archive_url, archive_extension, archive_root_dir)
        self.__template_dir = template_dir

    @property
    def template_dir(self):
        return self.__template_dir

class HadoopFramework(Framework):
    def __init__(self):
        super(HadoopFramework, self).__init__("hadoop", "Hadoop")

    def deploy(self, hadoop_home, framework_version, machines, settings, log_fn=util.log):
        """Deploys Hadoop to a given set of workers and a master node."""
        if len(machines) < 2:
            raise util.InvalidSetupError("Hadoop requires at least two machines: a master and at least one worker.")

        master = machines[0]
        workers = machines[1:]
        log_fn(0, "Selected Hadoop master \"%s\", with %d workers." % (master, len(workers)))

        # Ensure that HADOOP_HOME is an absolute path
        hadoop_home = os.path.realpath(hadoop_home)

        # Extract settings
        yarn_mb = settings.pop(_SETTING_YARN_MB, _DEFAULT_YARN_MB)
        java_home = settings.pop(_SETTING_JAVA_HOME)
        log_aggregation_str = str(settings.pop(_SETTING_LOG_AGGREGATION, _DEFAULT_LOG_AGGREGATION)).lower()
        log_aggregation = log_aggregation_str in ['true', 't', 'yes', 'y', '1']
        if len(settings) > 0:
            raise util.InvalidSetupError("Found unknown settings for Hadoop: '%s'" % "','".join(settings.keys()))

        # Generate configuration files using the included templates
        template_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "conf", "hadoop", framework_version.template_dir)
        config_dir = os.path.join(hadoop_home, "etc", "hadoop")
        substitutions = {
            "__USER__": os.environ["USER"],
            "__MASTER__": master,
            "__YARN_MB__": str(yarn_mb),
			"__LOG_AGGREGATION__": "true" if log_aggregation else "false"
        }
        if java_home:
            substitutions["${JAVA_HOME}"] = java_home
        substitutions_pattern = re.compile("|".join([re.escape(k) for k in substitutions.keys()]))
        # Iterate over template files and apply substitutions
        log_fn(1, "Generating configuration files...")
        for template_file in glob.glob(os.path.join(template_dir, "*.template")):
            template_filename = os.path.basename(template_file)[:-len(".template")]
            log_fn(2, "Generating file \"%s\"..." % template_filename)
            with open(template_file, "r") as template_in, open(os.path.join(config_dir, template_filename), "w") as config_out:
                for line in template_in:
                    print(substitutions_pattern.sub(lambda m: substitutions[m.group(0)], line.rstrip()), file=config_out)
        log_fn(2, "Generating file \"masters\"...")
        with open(os.path.join(config_dir, "masters"), "w") as masters_file:
            print(master, file=masters_file)
        log_fn(2, "Generating file \"slaves\"...")
        with open(os.path.join(config_dir, "slaves"), "w") as slaves_file:
            for worker in workers:
                print(worker, file=slaves_file)
        log_fn(2, "Configuration files generated.")

        # Clean up previous Hadoop deployments
        log_fn(1, "Creating a clean environment on the master and workers...")
        local_hadoop_dir = "/local/%s/hadoop/" % substitutions["__USER__"]
        log_fn(2, "Purging \"%s\" on master..." % local_hadoop_dir)
        util.execute_command_quietly(["ssh", master, 'rm -rf "%s"' % local_hadoop_dir])
        log_fn(2, "Purging \"%s\" on workers..." % local_hadoop_dir)
        for worker in workers:
            util.execute_command_quietly(['ssh', worker, 'rm -rf "%s"' % local_hadoop_dir])
        log_fn(2, "Creating directory structure on master...")
        util.execute_command_quietly(['ssh', master, 'mkdir -p "%s"' % local_hadoop_dir])
        log_fn(2, "Creating directory structure on workers...")
        for worker in workers:
            util.execute_command_quietly(['ssh', worker, 'mkdir -p "%s/tmp" "%s/datanode"' % (local_hadoop_dir, local_hadoop_dir)])
        log_fn(2, "Clean environment set up.")

        # Start HDFS
        log_fn(1, "Deploying HDFS...")
        log_fn(2, "Formatting namenode...")
        util.execute_command_quietly(['ssh', master, '"%s/bin/hadoop" namenode -format' % hadoop_home])
        log_fn(2, "Starting HDFS...")
        util.execute_command_quietly(['ssh', master, '"%s/sbin/start-dfs.sh"' % hadoop_home])

        # Start YARN
        log_fn(1, "Deploying YARN...")
        util.execute_command_quietly(['ssh', master, '"%s/sbin/start-yarn.sh"' % hadoop_home])

        log_fn(1, "Hadoop cluster deployed.")

    def get_supported_deployment_settings(self, framework_version):
        return _ALL_SETTINGS

get_framework_registry().register_framework(HadoopFramework())
get_framework_registry().framework("hadoop").add_version(HadoopFrameworkVersion("2.6.0", "http://ftp.tudelft.nl/apache/hadoop/core/hadoop-2.6.0/hadoop-2.6.0.tar.gz", "tar.gz", "hadoop-2.6.0", "2.6.x"))
