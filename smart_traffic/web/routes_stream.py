from flask import Blueprint, Response

import smart_traffic.state as state


bp_stream = Blueprint("stream", __name__)


def generate_frames(get_frame, condition):
    while True:
        with condition:
            condition.wait()
            frame = get_frame()
        if frame is not None:
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@bp_stream.route('/video_feed')
def video_feed():
    return Response(
        generate_frames(lambda: state.latest_frame_person, state.frame_condition_person),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@bp_stream.route('/video_feed_person')
def video_feed_person():
    return Response(
        generate_frames(lambda: state.latest_frame_person, state.frame_condition_person),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@bp_stream.route('/video_feed_car')
def video_feed_car():
    return Response(
        generate_frames(lambda: state.latest_frame_car, state.frame_condition_car),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
