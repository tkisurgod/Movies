const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());

// A simple health check route
app.get('/', (req, res) => res.send('Movies Backend is running without a database!'));

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
