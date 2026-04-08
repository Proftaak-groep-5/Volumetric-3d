import React from 'react';
import 'bootstrap/dist/css/bootstrap.css';

const Navbar = () => {
    return (
        <div>
            <b-navbar style="background-color: #66DE80" toggleable="lg">
                <b-navbar-brand>VolCap3D</b-navbar-brand>

            <b-navbar-toggle target="nav-collapse"></b-navbar-toggle>

            <b-collapse id="nav-collapse" is-nav="true">
                <b-navbar-nav>
                    <b-nav-item>Museums</b-nav-item>
                    <b-nav-item>Recordings</b-nav-item>
            </b-navbar-nav>

            <!-- Right aligned nav items -->
            <b-navbar-nav style="margin-left: auto;">
                <b-nav-item-dropdown text="User" right>
                    <!-- Gebruik 'button-content' slot -->
                    <template>
                    <em v-text="user?.name"></em>
                </template>
        </b-nav-item-dropdown>
        </b-navbar-nav>
        </b-collapse>
        </b-navbar>
        </div>
    );
};

export default Navbar;