import unittest
from hashlib import sha256
from string import printable

from mock import MagicMock, patch
from hypothesis import given, assume
from hypothesis.strategies import (
    dictionaries, fixed_dictionaries, integers, lists, text
)
from docker.client import DockerClient
from docker.errors import DockerException
from docker.models.images import Image
from docker.models.containers import Container
from requests.exceptions import ReadTimeout

from cdflow import (
    docker_run, get_image_sha, get_environment, _remove_container
)
from strategies import image_id, filepath, VALID_ALPHABET


class TestEnvironment(unittest.TestCase):

    @given(dictionaries(
        keys=text(alphabet=VALID_ALPHABET),
        values=text(alphabet=VALID_ALPHABET),
        min_size=1,
    ))
    def test_environment_contains_required_variables(self, environment):
        with patch('cdflow.os') as os:
            os.environ = environment

            container_environment = get_environment()

        assert 'AWS_ACCESS_KEY_ID' in container_environment
        assert 'AWS_SECRET_ACCESS_KEY' in container_environment
        assert 'AWS_SESSION_TOKEN' in container_environment
        assert 'FASTLY_API_KEY' in container_environment
        assert 'ROLE_SESSION_NAME' in container_environment


class TestImage(unittest.TestCase):

    @given(image_id())
    def test_get_sha(self, image_id):
        docker_client = MagicMock(spec=DockerClient)

        image_sha = '{}@sha256:{}'.format(
            image_id, sha256(image_id.encode('utf-8')).hexdigest()
        )

        image = MagicMock(spec=Image)
        image.attrs = {
            'RepoDigests': [image_sha]
        }

        docker_client.images.pull.return_value = image

        fetched_image_sha = get_image_sha(docker_client, image_id)

        assert fetched_image_sha == image_sha


class TestDockerRun(unittest.TestCase):

    @given(fixed_dictionaries({
        'environment_variables': fixed_dictionaries({
            'AWS_ACCESS_KEY_ID': text(alphabet=printable, min_size=10),
            'AWS_SECRET_ACCESS_KEY': text(alphabet=printable, min_size=10),
            'AWS_SESSION_TOKEN': text(alphabet=printable, min_size=10),
            'FASTLY_API_KEY': text(alphabet=printable, min_size=10),
            'CDFLOW_IMAGE_DIGEST': text(min_size=12),
        }),
        'image_id': image_id(),
        'project_root': filepath(),
        'command': lists(text(alphabet=printable)),
    }))
    def test_run_args(self, fixtures):
        docker_client = MagicMock(spec=DockerClient)
        image_id = fixtures['image_id']
        command = fixtures['command']
        project_root = fixtures['project_root']
        environment_variables = fixtures['environment_variables']

        container = MagicMock(spec=Container)
        container.attrs = {
            'State': {
                'ExitCode': 0
            }
        }
        docker_client.containers.run.return_value = container

        exit_status, output = docker_run(
            docker_client,
            image_id,
            command,
            project_root,
            environment_variables
        )

        assert exit_status == 0
        assert output == 'Done'

        docker_client.containers.run.assert_called_once_with(
            image_id,
            command=command,
            environment=environment_variables,
            detach=True,
            volumes={
                project_root: {
                    'bind': project_root,
                    'mode': 'rw',
                },
                '/var/run/docker.sock': {
                    'bind': '/var/run/docker.sock',
                    'mode': 'ro',
                },
            },
            working_dir=project_root,
        )

    @given(fixed_dictionaries({
        'environment_variables': fixed_dictionaries({
            'AWS_ACCESS_KEY_ID': text(alphabet=printable, min_size=10),
            'AWS_SECRET_ACCESS_KEY': text(alphabet=printable, min_size=10),
            'AWS_SESSION_TOKEN': text(alphabet=printable, min_size=10),
            'FASTLY_API_KEY': text(alphabet=printable, min_size=10),
            'CDFLOW_IMAGE_DIGEST': text(min_size=12),
        }),
        'image_id': image_id(),
        'project_root': filepath(),
        'command': lists(text(alphabet=printable)),
    }))
    def test_error_from_docker(self, fixtures):
        image_id = fixtures['image_id']
        command = fixtures['command']
        project_root = fixtures['project_root']
        environment_variables = fixtures['environment_variables']

        docker_client = MagicMock(spec=DockerClient)
        docker_client.containers.run.side_effect = DockerException

        exit_status, output = docker_run(
            docker_client,
            image_id,
            command,
            project_root,
            environment_variables
        )

        assert exit_status == 1
        assert output == str(DockerException())

    @given(fixed_dictionaries({
        'image_id': image_id(),
        'command': lists(text(alphabet=printable)),
        'project_root': filepath(),
        'environment_variables': dictionaries(
            keys=text(alphabet=VALID_ALPHABET),
            values=text(alphabet=VALID_ALPHABET),
            min_size=1,
        ),
    }))
    def test_follow_container_logs(self, fixtures):
        docker_client = MagicMock(spec=DockerClient)

        container = MagicMock(spec=Container)
        logs = MagicMock()
        messages = ['Running', 'the', 'command']
        logs.__iter__.return_value = iter(messages)
        container.logs.return_value = logs

        container.attrs = {
            'State': {
                'ExitCode': 0
            }
        }

        docker_client.containers.run.return_value = container

        with patch('cdflow.print') as print_:
            docker_run(
                docker_client, fixtures['image_id'], fixtures['command'],
                fixtures['project_root'], fixtures['environment_variables']
            )

            container.logs.assert_called_once_with(
                stream=True, follow=True, stdout=True, stderr=True
            )

            assert print_.call_args_list[0][1]['end'] == ''
            assert print_.call_args_list[0][0][0] == messages[0]
            assert print_.call_args_list[1][0][0] == messages[1]
            assert print_.call_args_list[2][0][0] == messages[2]

    @given(fixed_dictionaries({
        'image_id': image_id(),
        'command': lists(text(alphabet=printable)),
        'project_root': filepath(),
        'environment_variables': dictionaries(
            keys=text(alphabet=VALID_ALPHABET),
            values=text(alphabet=VALID_ALPHABET),
            min_size=1,
        ),
    }))
    def test_container_can_be_removed_at_script_exit(self, fixtures):
        docker_client = MagicMock(spec=DockerClient)
        container = MagicMock(spec=Container)
        container.attrs = {
            'State': {
                'ExitCode': 0
            }
        }

        docker_client.containers.run.return_value = container

        with patch('cdflow.atexit') as atexit:
            docker_run(
                docker_client, fixtures['image_id'], fixtures['command'],
                fixtures['project_root'], fixtures['environment_variables']
            )

            atexit.register.assert_called_once_with(
                _remove_container, container
            )

    def test_remove_container(self):
        container = MagicMock(spec=Container)

        _remove_container(container)

        container.stop.assert_called_once_with()
        container.remove.assert_called_once_with()

    def test_remove_still_running_container(self):
        container = MagicMock(spec=Container)

        container.stop.side_effect = ReadTimeout

        try:
            _remove_container(container)
        except Exception as e:
            self.fail('Exception was raised: {}'.format(e))

        container.stop.assert_called_once_with()
        container.remove.assert_called_once_with()

    @given(fixed_dictionaries({
        'image_id': image_id(),
        'command': lists(text(alphabet=printable)),
        'project_root': filepath(),
        'environment_variables': dictionaries(
            keys=text(alphabet=VALID_ALPHABET),
            values=text(alphabet=VALID_ALPHABET),
            min_size=1,
        ),
        'exit_code': integers(min_value=-255, max_value=256),
    }))
    def test_exit_code_from_container_is_returned(self, fixtures):
        assume(fixtures['exit_code'] != 0)
        docker_client = MagicMock(spec=DockerClient)
        container = MagicMock(spec=Container)

        container.attrs = {
            'State': {
                'ExitCode': fixtures['exit_code'],
            }
        }

        docker_client.containers.run.return_value = container

        exit_status, output = docker_run(
            docker_client, fixtures['image_id'], fixtures['command'],
            fixtures['project_root'], fixtures['environment_variables']
        )

        assert exit_status == fixtures['exit_code']
        assert output == 'Error'
