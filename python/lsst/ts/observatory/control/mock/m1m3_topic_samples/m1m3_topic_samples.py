# This file is part of ts_observatory_control.
#
# Developed for the Vera Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

__all__ = [
    "get_m1m3_topic_samples_data",
    "get_m1m3_topic_samples_data_path",
]

import glob
import os.path
import pathlib
import typing

import yaml


def get_m1m3_topic_samples_data_path() -> pathlib.Path:
    """Return Path to the current directory."""
    return pathlib.Path(__file__).resolve().parents[0]


def get_m1m3_topic_samples_data() -> (
    typing.Dict[
        str,
        typing.Dict[
            str,
            typing.Union[
                int,
                float,
                str,
            ],
        ],
    ]
):
    """Get all M1M3 topic data samples.

    Returns
    -------
    m1m3_topic_samples : dict
        Dictionary with topic name as key and sample data (dictionary from
        yaml) as value.
    """
    m1m3_topic_samples = dict()

    for topic_sample_file in glob.glob(
        (get_m1m3_topic_samples_data_path() / "*_sample.yaml").as_posix()
    ):
        with open(topic_sample_file) as fp:
            data = yaml.safe_load(fp)

        # remove private fields.
        private_fields = [field for field in data if field.startswith("private_")]

        for field in private_fields:
            data.pop(field)

        topic_name = os.path.splitext(os.path.basename(topic_sample_file))[0].split(
            "_"
        )[0]

        m1m3_topic_samples[topic_name] = data

    return m1m3_topic_samples
