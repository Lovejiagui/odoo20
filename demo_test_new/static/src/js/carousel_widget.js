/** @odoo-module **/
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";

class CarouselWidget extends Component {
    static template = "demo_test_new.CarouselWidget";

    setup() {
        this.state = useState({
            index: 0,
            imgList: [
                { id: 1, src: "/demo_test_new/static/src/img/1.png" },
                { id: 2, src: "/demo_test_new/static/src/img/2.jpg" },
                { id: 3, src: "/demo_test_new/static/src/img/3.jpg" },
            ],
        });
        this.timer = null;
    }

    // 鼠标进入，停止自动轮播
    onMouseEnter() {
        if(this.timer){
            clearInterval(this.timer);
            this.timer = null;
        }
    }
    // 鼠标离开，重新开启自动轮播
    onMouseLeave() {
        this.timer = setInterval(()=>{
            this.nextImg();
        },3000);
    }

    prevImg() {
        if (this.state.index > 0) {
            this.state.index -= 1;
        } else {
            this.state.index = this.state.imgList.length - 1;
        }
    }

    nextImg() {
        if (this.state.index < this.state.imgList.length - 1) {
            this.state.index += 1;
        } else {
            this.state.index = 0;
        }
    }
}

registry.category("fields").add("carousel_widget", {
    component: CarouselWidget,
});
