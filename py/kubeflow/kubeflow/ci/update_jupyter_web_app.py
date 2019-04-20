"""Script to build and update the Jupyter WebApp image."""

import fire
import git
import httplib2
import json
import logging
import os
import re
import tempfile
import yaml

from kubeflow.testing import util

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2_2 import docker_digest
from containerregistry.client.v2_2 import docker_http
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.transport import transport_pool
from containerregistry.transform.v2_2 import metadata

class WebAppUpdater(object):
  def build_image(self, project):
    """Build the image."""
    env = dict()
    env.update(os.environ)
    env["PROJECT"] = project

    with tempfile.NamedTemporaryFile() as hf:
      name = hf.name
    env["OUTPUT"] = name
    web_dir = self._component_dir()
    util.run(["make", "build-gcb"], env=env, cwd=web_dir)

    with open(name) as hf:
      data = yaml.load(hf)

    return data["image"]

  def update_prototype(self, image):
    values = {"image": image}

    regexps = {}
    for param, value in values.iteritems():
      r = re.compile(r"([ \t]*" + param + ":+ ?\"?)[^\",]+(\"?,?)")
      v = r"\g<1>" + value + r"\2"
      regexps[param] = (r, v, value)

    prototype_file = os.path.join(self._root_dir(),
                                  "kubeflow/jupyter/prototypes",
                                  "jupyter-web-app.jsonnet")
    with open(prototype_file) as f:
      prototype = f.read().split("\n")
    replacements = 0
    for i, line in enumerate(prototype):
      for param in regexps.keys():
        if param not in line:
          continue
        if line.startswith("//"):
          prototype[i] = re.sub(
            r"(// @\w+ )" + param + r"( \w+ )[^ ]+(.*)",  # noqa: W605
            r"\g<1>" + param + r"\2" + regexps[param][2] + r"\3",
            line)
          replacements += 1
          continue
        prototype[i] = re.sub(regexps[param][0], regexps[param][1], line)
        if line != prototype[i]:
          replacements += 1
    if replacements == 0:
      raise Exception(
          "No replacements made, are you sure you specified correct param?")
    if replacements < len(regexps):
      raise Warning("Made less replacements then number of params. Typo?")
    temp_file = prototype_file + ".tmp"
    with open(temp_file, "w") as w:
      w.write("\n".join(prototype))
    os.rename(temp_file, prototype_file)
    logging.info("Successfully made %d replacements" % replacements)

  def all(self, project):
    # TODO(jlewi): Get the latest image and compare the sha against the
    # current sha and if it isn't the same then rebuild the image.
    # TODO(jlewi): We might actually want to use git diff to see the
    # the last commit the relevant code actually changed.
    base_image = "gcr.io/{0}/jupyter-web-app:latest".format(project)
    transport = transport_pool.Http(httplib2.Http)
    src = docker_name.from_string(base_image)
    creds = docker_creds.DefaultKeychain.Resolve(src)
    try:
      with v2_2_image.FromRegistry(src, creds, transport) as src_image:
        config = json.loads(src_image.config_file())
    except docker_http.V2DiagnosticException as e:
      if e.status == 404:
        logging.info("%s doesn't exist", base_image)
      else:
        raise
    git_version = config.get("container_config").get("Labels").get("git-version")
    logging.info("Most recent image has git-version %s", git_version)

    last_hash = None
    if git_version:
      last_hash = git_version.rsplit("g", 1)[-1]

    repo = git.Repo(self._root_dir())
    last_commit = repo.commit().hexsha[0:8]

    if last_hash == last_commit:
      logging.info("Existing docker image is already built from commit: %s",
                   last_commit)

    else:
      image = self.build_image(project)

    # TODO(jlewi):We should check what the current image and not update it
    # if its the existing image
    self.update_prototype(image)

  def _root_dir(self):
    this_dir = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(this_dir, "..", "..", "..", ".."))

  def _component_dir(self):
    return os.path.join(self._root_dir(), "components", "jupyter-web-app")

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO,
                      format=('%(levelname)s|%(asctime)s'
                              '|%(pathname)s|%(lineno)d| %(message)s'),
                      datefmt='%Y-%m-%dT%H:%M:%S',
                      )
  logging.getLogger().setLevel(logging.INFO)
  fire.Fire(WebAppUpdater)