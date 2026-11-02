// CI pipeline for collectors/openalex_kz.py
// Every commit -> unit tests (in Docker) -> build runtime Docker image -> smoke test of the image.
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    triggers {
        githubPush()                 // instant build on push if a GitHub webhook reaches Jenkins
        pollSCM('H/2 * * * *')       // fallback for local Jenkins without a public URL
    }

    environment {
        IMAGE    = 'openalex-kz'
        TAG      = "${env.BUILD_NUMBER}"
        TEST_CTR = "openalex-kz-test-${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_SHORT = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim()
                }
                echo "Commit ${env.GIT_SHORT}"
            }
        }

        stage('Unit tests') {
            steps {
                sh 'docker build --target test -t $IMAGE:test-$TAG .'
                sh 'docker rm -f $TEST_CTR >/dev/null 2>&1 || true'
                sh 'docker run --name $TEST_CTR $IMAGE:test-$TAG'
            }
            post {
                always {
                    sh 'mkdir -p reports && docker cp $TEST_CTR:/app/reports/junit.xml reports/junit.xml || true'
                    sh 'docker rm -f $TEST_CTR >/dev/null 2>&1 || true'
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                }
            }
        }

        stage('Build Docker image') {
            steps {
                sh 'docker build --target runtime -t $IMAGE:$TAG -t $IMAGE:$GIT_SHORT -t $IMAGE:latest .'
                sh 'docker image ls $IMAGE'
            }
        }

        stage('Smoke test image') {
            steps {
                sh '''docker run --rm --entrypoint python $IMAGE:$TAG -c \
                      "import collectors.openalex_kz as m; print('OK, API base:', m.BASE)"'''
            }
        }
    }

    post {
        always {
            sh 'docker image rm $IMAGE:test-$TAG >/dev/null 2>&1 || true'
        }
        success { echo "Built image ${env.IMAGE}:${env.TAG} (${env.GIT_SHORT})" }
        failure { echo 'Pipeline failed - see the stage log above.' }
    }
}
