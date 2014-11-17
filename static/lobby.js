
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
    });
});
