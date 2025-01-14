"""
 Copyright (c) 2021-2023 Intel Corporation

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""
from .image_model import ImageModel
from .types import ListValue, NumericalValue, StringValue
from .utils import clip_detections, load_labels


class DetectionModel(ImageModel):
    """An abstract wrapper for object detection model

    The DetectionModel must have a single image input.
    It inherits `preprocess` from `ImageModel` wrapper. Also, it defines `_resize_detections` method,
    which should be used in `postprocess`, to clip bounding boxes and resize ones to original image shape.

    The `postprocess` method must be implemented in a specific inherited wrapper.
    """

    def __init__(self, inference_adapter, configuration=None, preload=False):
        """Detection Model constructor

        It extends the `ImageModel` construtor.

        Args:
            inference_adapter (InferenceAdapter): allows working with the specified executor
            configuration (dict, optional): it contains values for parameters accepted by specific
              wrapper (`confidence_threshold`, `labels` etc.) which are set as data attributes
            preload (bool, optional): a flag whether the model is loaded to device while
              initialization. If `preload=False`, the model must be loaded via `load` method before inference

        Raises:
            WrapperError: if the model has more than 1 image inputs
        """

        super().__init__(inference_adapter, configuration, preload)

        if not self.image_blob_name:
            self.raise_error(
                "The Wrapper supports only one image input, but {} found".format(
                    len(self.image_blob_names)
                )
            )

        if self.path_to_labels:
            self.labels = load_labels(self.path_to_labels)

    @classmethod
    def parameters(cls):
        parameters = super().parameters()
        parameters.update(
            {
                "confidence_threshold": NumericalValue(
                    default_value=0.5,
                    description="Probability threshold value for bounding box filtering",
                ),
                "labels": ListValue(description="List of class labels"),
                "path_to_labels": StringValue(
                    description="Path to file with labels. Overrides the labels, if they sets via 'labels' parameter"
                ),
            }
        )

        return parameters

    def _resize_detections(self, detections, meta):
        """Resizes detection bounding boxes according to initial image shape.

        It implements image resizing depending on the set `resize_type`(see `ImageModel` for details).
        Next, it applies bounding boxes clipping.

        Args:
            detections (List[Detection]): list of detections with coordinates in normalized form
            meta (dict): the input metadata obtained from `preprocess` method

        Returns:
            - list of detections with resized and clipped coordinates fit to initial image

        Raises:
            WrapperError: If the model uses custom resize or `resize_type` is not set
        """
        resized_shape = meta["resized_shape"]
        original_shape = meta["original_shape"]

        if self.resize_type == "fit_to_window_letterbox":
            detections = resize_detections_letterbox(
                detections, original_shape[1::-1], resized_shape[1::-1]
            )
        elif self.resize_type == "fit_to_window":
            detections = resize_detections_with_aspect_ratio(
                detections,
                original_shape[1::-1],
                resized_shape[1::-1],
                (self.w, self.h),
            )
        elif self.resize_type == "standard":
            detections = resize_detections(detections, original_shape[1::-1])
        else:
            self.raise_error("Unknown resize type {}".format(self.resize_type))
        return clip_detections(detections, original_shape)

    def _add_label_names(self, detections):
        """Adds labels names to detections if they are available

        Args:
            detections (List[Detection]): list of detections with coordinates in normalized form

        Returns:
            - list of detections with label strings
        """
        for detection in detections:
            detection.str_label = self.get_label_name(detection.id)
        return detections


def resize_detections(detections, original_image_size):
    for detection in detections:
        detection.xmin *= original_image_size[0]
        detection.xmax *= original_image_size[0]
        detection.ymin *= original_image_size[1]
        detection.ymax *= original_image_size[1]
    return detections


def resize_detections_with_aspect_ratio(
    detections, original_image_size, resized_image_size, model_input_size
):
    scale_x = model_input_size[0] / resized_image_size[0] * original_image_size[0]
    scale_y = model_input_size[1] / resized_image_size[1] * original_image_size[1]
    for detection in detections:
        detection.xmin *= scale_x
        detection.xmax *= scale_x
        detection.ymin *= scale_y
        detection.ymax *= scale_y
    return detections


def resize_detections_letterbox(detections, original_image_size, resized_image_size):
    inverted_scale = max(
        original_image_size[0] / resized_image_size[0],
        original_image_size[1] / resized_image_size[1],
    )
    pad_left = (resized_image_size[0] - original_image_size[0] / inverted_scale) // 2
    pad_top = (resized_image_size[1] - original_image_size[1] / inverted_scale) // 2
    for detection in detections:
        detection.xmin = (
            detection.xmin * resized_image_size[0] - pad_left
        ) * inverted_scale
        detection.ymin = (
            detection.ymin * resized_image_size[1] - pad_top
        ) * inverted_scale
        detection.xmax = (
            detection.xmax * resized_image_size[0] - pad_left
        ) * inverted_scale
        detection.ymax = (
            detection.ymax * resized_image_size[1] - pad_top
        ) * inverted_scale
    return detections
