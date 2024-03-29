import java.text.SimpleDateFormat
jobName = "python-marvin"
version = "0.1.97"
build_dir = "deb_dist"

@Library('jenkins-shared') _

node {
    try {
        notifyBuild('STARTED')
        // Be sure that workspace is cleaned
        deleteDir()
        stage ('Git') {
            git branch: 'master', url: 'git@github.com:MONROE-PROJECT/Scheduler.git'
            gitCommit = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
            shortCommit = gitCommit.take(6)
            commitChangeset = sh(returnStdout: true, script: 'git diff-tree --no-commit-id --name-status -r HEAD').trim()
            commitMessage = sh(returnStdout: true, script: "git show ${gitCommit} --format=%B --name-status").trim()
            sh """echo "${commitMessage}" > CHANGELIST"""
            def dateFormat = new SimpleDateFormat("yyyyMMddHHmm")
            def date = new Date()
            def timestamp = dateFormat.format(date).toString()
            checkout([$class: 'GitSCM',
                    branches: [[name: 'monroe']],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'versionize']],
                    submoduleCfg: [],
                    userRemoteConfigs: [[url: 'git@github.com:Celerway/celerway-jenkins.git']]])
        }
        withDockerRegistry(credentialsId: 'gcr:nimbus-tools-gcr', url: 'http://eu.gcr.io/nimbus-tools') {
            docker.image('eu.gcr.io/nimbus-tools/monroe-builder:stretch').inside('-u jenkins') {
                
                stage ('Build') {
                  sh "python setup.py --command-packages=stdeb.command bdist_deb"

                  sh """chmod +x versionize/versionize.sh
                  cp versionize/versionize.sh deb_dist/
                  # Sticky bit is set on directory during build. Removing it.
                  chmod -R g-s deb_dist"""

                  dir(build_dir) {
                    sh "./versionize.sh ${jobName}_0.1.0-1_all.deb ${jobName} ${version} ${shortCommit}"
                    sh "rm ${jobName}_0.1.0-1_all.deb"
                  }
                }
             }

            stage ('Archive artifacts') {
                archiveArtifacts "${build_dir}/*.deb"
            }
        }
    } catch (e) {
        currentBuild.result = "FAILED"
        throw e
    } finally {
        // Success or failure, always send notifications
        notifyBuild(currentBuild.result)
    } // end of try catch finally block
}
