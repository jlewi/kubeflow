"""Script to build and update the Jupyter WebApp image."""

import fire
import logging
import os
import re
import tempfile
import yaml

from kubeflow.testing import util

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
    regexps = {"image": image}

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
    image = self.build_image(project)
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