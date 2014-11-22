
var socket = new WebSocket("ws://" + location.host + "/chatsocket");

$.fn.serializeObject = function()
{
    var o = {};
    var a = this.serializeArray();
    $.each(a, function() {
        if (o[this.name] !== undefined) {
            if (!o[this.name].push) {
                o[this.name] = [o[this.name]];
            }
            o[this.name].push(this.value || '');
        } else {
            o[this.name] = this.value || '';
        }
    });
    return o;
};

socket.onmessage = function(event)
{
    var msg = JSON.parse(event.data);
    $("#inbox").append(msg.html);
}

$(document).ready(function() {
    $("#messagebutton").click(function(){
        socket.send(JSON.stringify($("#messageform").serializeObject()));
        document.getElementById("message").value = "";
    });
});

function submitChatForm()
{
    socket.send(JSON.stringify($("#messageform").serializeObject()));
    document.getElementById("message").value = "";
    return false;
}

var finding_match = false;
var queue_socket

$(document).ready(function() {
    $("#findmatchbutton").click(function(){
        finding_match = !finding_match;
        if(finding_match) {
            document.getElementById("findmatchbutton").value = "Cancel Search";
            document.getElementById("matchprogress").style = "";

            queue_socket = new WebSocket("ws://" + location.host + "/queuesocket");
            queue_socket.onmessage = function(event)
            {
                document.getElementById("findmatchbutton").value = "Find Match";
                document.getElementById("matchprogress").style = "display: none";
                queue_socket.close();
                $("#match_found_message").show(2000);
                var data = JSON.parse(event.data);
                window.location.replace("match/" + data["match_id"]);
            }
        }
        else {
            document.getElementById("findmatchbutton").value = "Find Match";
            document.getElementById("matchprogress").style = "display: none";
            queue_socket.close();
        }
    });
});
