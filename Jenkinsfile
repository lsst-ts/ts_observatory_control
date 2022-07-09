pipeline {
    agent any
    options {
      disableConcurrentBuilds(
        abortPrevious: true,
      )
    }
    environment {
        network_name = "n_${BUILD_ID}_${JENKINS_NODE_COOKIE}"
        container_name = "c_${BUILD_ID}_${JENKINS_NODE_COOKIE}"
        work_branches = "${GIT_BRANCH} ${CHANGE_BRANCH} develop"
        LSST_IO_CREDS = credentials("lsst-io")
    }

    stages {
        stage("Pulling docker image") {
            steps {
                script {
                    sh """
                    docker pull lsstts/salobj:develop
                    """
                }
            }
        }
        stage("Preparing environment") {
            steps {
                script {
                    sh """
                    docker network create \${network_name}
                    chmod -R a+rw \${WORKSPACE}
                    container=\$(docker run -v \${WORKSPACE}:/home/saluser/repo/ -td --rm --net \${network_name} -e LTD_USERNAME=\${LSST_IO_CREDS_USR} -e LTD_PASSWORD=\${LSST_IO_CREDS_PSW} --name \${container_name} lsstts/salobj:develop)
                    """
                }
            }
        }
        stage("Checkout sal") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && cd /home/saluser/repos/ts_sal && git fetch -p && git reset --hard origin/develop && /home/saluser/.checkout_repo.sh \${work_branches} && git pull\"
                    """
                }
            }
        }
        stage("Checkout salobj") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && cd /home/saluser/repos/ts_salobj && git fetch -p && /home/saluser/.checkout_repo.sh \${work_branches} && git pull\"
                    """
                }
            }
        }
        stage("Checkout xml") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && cd /home/saluser/repos/ts_xml && git fetch -p && /home/saluser/.checkout_repo.sh \${work_branches} && git pull\"
                    """
                }
            }
        }
        stage("Checkout IDL") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && cd /home/saluser/repos/ts_idl && git fetch -p && /home/saluser/.checkout_repo.sh \${work_branches} && git pull\"
                    """
                }
            }
        }
        stage("Build IDL files") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && make_idl_files.py --all\"
                    """
                }
            }
        }
        stage("Checkout git-lfs files") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && cd /home/saluser/repo/ && eups declare -r . -t saluser && setup ts_observatory_control -t saluser && export LSST_DDS_IP=192.168.0.1 && printenv LSST_DDS_IP && git lfs install && git lfs fetch --all && git lfs checkout\"
                    """
                }
            }
        }
        stage("Running tests") {
            steps {
                script {
                    sh """
                    docker exec -u saluser \${container_name} sh -c \"source ~/.setup.sh && cd /home/saluser/repo/ && eups declare -r . -t saluser && setup ts_observatory_control -t saluser && export LSST_DDS_IP=192.168.0.1 && printenv LSST_DDS_IP && pytest -v --color=no --junitxml=tests/.tests/junit.xml\"
                    """
                }
            }
        }
// This next step would start a build of ts_standardscripts. This need a bit
// more work to sort the branches right. I will leave it here for future
// reference.
//         stage("Build dependency - ts_standardscripts") {
//            steps {
//                build job: 'LSST_Telescope-and-Site/ts_standardscripts/develop', parameters: [stringParam(name: 'CHANGE_BRANCH', value: "${work_branches}")], wait: false
//            }
//         }
    }
    post {
        always {
            // The path of xml needed by JUnit is relative to
            // the workspace.
            junit 'tests/.tests/junit.xml'

            // Publish the HTML report
            publishHTML (target: [
                allowMissing: false,
                alwaysLinkToLastBuild: false,
                keepAll: true,
                reportDir: 'tests/.tests/',
                reportFiles: 'index.html',
                reportName: "Coverage Report"
              ])

              script {

                  def RESULT = sh returnStatus: true, script: "docker exec -u saluser \${container_name} sh -c \"" +
                      "source ~/.setup.sh && " +
                      "cd /home/saluser/repo/ && " +
                      "setup ts_observatory_control -t saluser && " +
                      "pip install -r doc/requirements.txt && " +
                      "package-docs build &&" +
                      "ltd upload --product ts-observatory-control --git-ref \${GIT_BRANCH} --dir doc/_build/html\""

                  if ( RESULT != 0 ) {
                      echo("Failed to build/push documentation.")
                  }
               }
        }
        cleanup {
            sh """
                docker exec -u root --privileged \${container_name} sh -c \"chmod -R a+rw /home/saluser/repo/ \"
                docker stop \${container_name} || echo Could not stop container
                docker network rm \${network_name} || echo Could not remove network
            """
            deleteDir()
        }
    }
}
